import os
from io import BytesIO
from datetime import datetime

import numpy as np
from flask import current_app

from app.extensions import db
from app.models.student import Student
from app.models.voice_embedding import VoiceEmbedding


# The VoiceEncoder model is loaded once per process (not per-request) - it's
# small (~17MB) and loading it is cheap, but re-loading on every request would
# still add unnecessary latency.
_voice_encoder = None


def _get_encoder():
    global _voice_encoder
    if _voice_encoder is None:
        from resemblyzer import VoiceEncoder
        _voice_encoder = VoiceEncoder()
    return _voice_encoder


def _load_wav_as_float_array(file_storage):
    """Converts any browser/uploaded audio format (webm, ogg, wav, ...) into
    a mono float32 waveform at 16kHz, which is what Resemblyzer expects."""
    if file_storage is None:
        return None

    file_storage.seek(0)
    audio_bytes = file_storage.read()

    try:
        from pydub import AudioSegment

        audio_segment = AudioSegment.from_file(BytesIO(audio_bytes))
        audio_segment = audio_segment.set_frame_rate(16000).set_channels(1)

        samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)

        # normalize int16 PCM range to [-1, 1]
        max_val = float(1 << (8 * audio_segment.sample_width - 1))
        samples = samples / max_val

        return samples
    except Exception:
        return None


def extract_voice_embedding(file_storage):
    """Returns a 256-dim speaker embedding, or None if the audio is too
    short/invalid to process."""
    wav = _load_wav_as_float_array(file_storage)

    if wav is None or len(wav) < 16000 * 1.5:  # require at least ~1.5s of audio
        return None

    try:
        from resemblyzer import preprocess_wav

        processed = preprocess_wav(wav, source_sr=16000)

        if processed is None or len(processed) == 0:
            return None

        encoder = _get_encoder()
        embedding = encoder.embed_utterance(processed)
        return embedding
    except Exception:
        return None


def save_voice_file(roll_number, file_storage):
    folder = os.path.join(current_app.config["VOICE_UPLOAD_FOLDER"], roll_number)
    os.makedirs(folder, exist_ok=True)

    filename = datetime.now().strftime("%Y%m%d_%H%M%S") + ".wav"
    path = os.path.join(folder, filename)

    file_storage.seek(0)
    try:
        from pydub import AudioSegment
        audio_segment = AudioSegment.from_file(file_storage)
        audio_segment.export(path, format="wav")
    except Exception:
        file_storage.seek(0)
        with open(path, "wb") as f:
            f.write(file_storage.read())

    return path


def enroll_student_voice(roll_number, file_storage):
    student = Student.query.filter_by(roll_number=(roll_number or "").strip()).first()
    if student is None:
        return False, "Student roll number not found."

    if file_storage is None:
        return False, "Please record student voice first."

    embedding = extract_voice_embedding(file_storage)
    if embedding is None:
        return False, "Voice sample too short/invalid. Record at least 2-3 seconds of clear speech."

    path = save_voice_file(student.roll_number, file_storage)

    voice_embedding = VoiceEmbedding(student_id=student.id, audio_path=path)
    voice_embedding.set_embedding(embedding)

    db.session.add(voice_embedding)
    db.session.commit()

    return True, "Student voice enrolled successfully."


def detect_narrow_bandwidth_signal(wav_array, sample_rate=16000):
    """Additional (advisory, not blocking) anti-spoofing signal: checks
    whether the audio's energy is concentrated in an unusually narrow
    frequency band, which can indicate audio that was played through a
    small speaker and re-captured (small speakers often roll off below
    ~150Hz and above ~7-8kHz) rather than a live human voice captured
    directly by a phone/laptop mic (typically much flatter response).

    IMPORTANT - why this is advisory, not a hard block: a real recording
    made on a cheap microphone, in a noisy room, or with aggressive codec
    compression can ALSO show a narrow effective bandwidth, with no spoofing
    involved. This heuristic's false-positive rate on real student recordings
    is unknown and unvalidated. It surfaces a flag for the teacher's
    awareness rather than auto-rejecting attendance.

    Returns (is_suspicious, bandwidth_hz).
    """
    if wav_array is None or len(wav_array) == 0:
        return False, 0.0

    spectrum = np.abs(np.fft.rfft(wav_array))
    freqs = np.fft.rfftfreq(len(wav_array), d=1 / sample_rate)

    total_energy = np.sum(spectrum)
    if total_energy == 0:
        return False, 0.0

    # Find the frequency band containing the central 90% of spectral energy.
    cumulative = np.cumsum(spectrum)
    low_idx = np.searchsorted(cumulative, 0.05 * total_energy)
    high_idx = np.searchsorted(cumulative, 0.95 * total_energy)

    bandwidth_hz = float(freqs[min(high_idx, len(freqs) - 1)] - freqs[low_idx])

    # Conservative threshold - chosen to flag clearly narrow-band audio
    # (e.g. under ~2.5kHz effective bandwidth) while trying not to flag
    # normal speech, which typically spans several kHz. Not independently
    # validated against real spoofing recordings.
    SUSPICION_BANDWIDTH_HZ = 2500.0

    return bandwidth_hz < SUSPICION_BANDWIDTH_HZ, bandwidth_hz



def _speech_segments(wav_array, sample_rate=16000, frame_ms=40):
    """Return contiguous speech-like segments as (start_sec, end_sec).

    This deliberately uses only an RMS energy envelope so active voice
    liveness does not depend on a cloud speech-to-text API. It is not intended
    to understand words; it verifies the randomized *timing pattern* shown to
    the user (short/long utterance separated by a pause).
    """
    if wav_array is None or len(wav_array) == 0:
        return []

    wav = np.asarray(wav_array, dtype=np.float32)
    frame_len = max(1, int(sample_rate * frame_ms / 1000))
    usable = len(wav) - (len(wav) % frame_len)
    if usable < frame_len:
        return []

    frames = wav[:usable].reshape(-1, frame_len)
    rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    peak = float(np.max(rms))
    if peak < 0.003:
        return []

    noise_floor = float(np.percentile(rms, 10))
    threshold = max(0.008, noise_floor * 2.5, peak * 0.16)
    active = rms >= threshold

    # Fill tiny gaps (<~160ms) inside an utterance; natural speech has brief
    # consonant gaps that should not split one segment into many pieces.
    max_gap_frames = max(1, int(160 / frame_ms))
    idx = 0
    while idx < len(active):
        if active[idx]:
            idx += 1
            continue
        gap_start = idx
        while idx < len(active) and not active[idx]:
            idx += 1
        gap_len = idx - gap_start
        if gap_start > 0 and idx < len(active) and gap_len <= max_gap_frames:
            active[gap_start:idx] = True

    segments = []
    idx = 0
    while idx < len(active):
        if not active[idx]:
            idx += 1
            continue
        start = idx
        while idx < len(active) and active[idx]:
            idx += 1
        end = idx
        duration = (end - start) * frame_ms / 1000.0
        if duration >= 0.20:
            segments.append((start * frame_ms / 1000.0, end * frame_ms / 1000.0))

    return segments


def verify_voice_liveness_pattern(wav_array, pattern):
    """Verify a randomized two-utterance timing challenge.

    ``short_long``: short sound -> pause -> long sound
    ``long_short``: long sound -> pause -> short sound

    A static saved recording is much less reusable because the server chooses
    the pattern immediately before each attempt. This is still a basic active
    liveness check (not a dedicated replay-attack classifier), but it is
    meaningfully stronger than an exact-file SHA hash alone.
    """
    segments = _speech_segments(wav_array)
    if len(segments) != 2:
        return False, "Voice liveness needs exactly two clear sounds separated by a pause. Please retry the displayed challenge."

    durations = [end - start for start, end in segments]
    pause = segments[1][0] - segments[0][1]
    if pause < 0.30:
        return False, "Pause between the two challenge sounds was too short. Please retry."

    first, second = durations
    short_ok = lambda value: 0.25 <= value <= 1.30
    long_ok = lambda value: 1.20 <= value <= 3.80

    if pattern == "short_long":
        ok = short_ok(first) and long_ok(second) and second >= first * 1.45
    elif pattern == "long_short":
        ok = long_ok(first) and short_ok(second) and first >= second * 1.45
    else:
        return False, "Unknown voice liveness challenge."

    if not ok:
        return False, "Voice timing did not match the randomized liveness challenge. Please retry with the shown short/long pattern."

    return True, "Voice active-liveness challenge passed."

def _hash_audio_bytes(file_storage):
    import hashlib

    file_storage.seek(0)
    audio_bytes = file_storage.read()
    file_storage.seek(0)
    return hashlib.sha256(audio_bytes).hexdigest()


def check_audio_replay(file_storage, subject_id, challenge_nonce=None):
    """Basic anti-replay check: rejects a recognition attempt if the exact
    same audio BYTES were already submitted before for this subject.

    WHAT THIS CATCHES: someone re-uploading/re-submitting a previously
    captured audio file as-is (e.g. intercepting and resending a network
    request, or reusing a saved .wav file directly through the API).

    This exact-file check is now a secondary control. Voice recognition also
    requires a signed randomized short/long active-liveness timing challenge;
    ``challenge_nonce`` is stored here and can be consumed only once, so an
    intercepted valid request cannot simply be replayed with re-encoded audio.
    A sophisticated attacker can still synthesize a new recording that follows
    the requested timing pattern, so this remains basic liveness rather than
    certified presentation-attack detection.

    Returns (is_new, message).
    """
    from app.models.voice_recognition_log import VoiceRecognitionLog
    from app.extensions import db

    audio_hash = _hash_audio_bytes(file_storage)

    existing = VoiceRecognitionLog.query.filter_by(
        audio_hash=audio_hash, subject_id=subject_id
    ).first()

    if existing is not None:
        return False, "This exact audio has already been submitted before (possible replay attempt). Please record a fresh sample."

    if challenge_nonce:
        reused_challenge = VoiceRecognitionLog.query.filter_by(challenge_nonce=challenge_nonce).first()
        if reused_challenge is not None:
            return False, "This voice liveness challenge has already been used. Please request a fresh challenge and record again."

    db.session.add(VoiceRecognitionLog(
        audio_hash=audio_hash, subject_id=subject_id, challenge_nonce=challenge_nonce
    ))
    db.session.commit()

    return True, "OK"


def cosine_similarity(a, b):
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def recognize_voice(file_storage, enrolled_students):
    if file_storage is None:
        return False, "Please record student voice first.", []

    current_embedding = extract_voice_embedding(file_storage)
    if current_embedding is None:
        return False, "Voice sample too short/invalid. Record at least 2-3 seconds.", []

    # Cosine-similarity operating threshold. It was selected after running
    # scripts/evaluate_voice_accuracy.py on
    # synthetic data (see EVALUATION.md). The raw Equal Error Rate point was
    # ~0.58 (FAR=FRR=8.3%); this is set higher, at 0.65, to bias toward fewer
    # false accepts (marking an unenrolled/wrong student present) at the cost
    # of a somewhat higher false-reject rate. Must be re-tuned once real
    # recorded voice samples are available - synthetic audio does not fully
    # represent real speech variability.
    SIMILARITY_THRESHOLD = 0.65

    best_student_id = None
    best_similarity = -1.0

    for student in enrolled_students:
        for emb_row in student.voice_embeddings:
            saved_embedding = emb_row.get_embedding()
            similarity = cosine_similarity(current_embedding, saved_embedding)

            if similarity > best_similarity:
                best_similarity = similarity
                best_student_id = student.id

    preview = []
    for student in enrolled_students:
        is_match = student.id == best_student_id and best_similarity >= SIMILARITY_THRESHOLD
        preview.append(
            {
                "student_id": student.id,
                "student_name": student.name,
                "roll_number": student.roll_number,
                "status": "Present" if is_match else "Absent",
                "confidence": round(best_similarity, 3) if student.id == best_student_id else None,
            }
        )

    return True, "Voice attendance preview generated using speaker embeddings.", preview

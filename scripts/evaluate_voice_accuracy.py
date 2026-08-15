"""
Voice recognition accuracy evaluation: computes False Accept Rate (FAR),
False Reject Rate (FRR), and Equal Error Rate (EER) across a range of
similarity thresholds.

IMPORTANT LIMITATION: This script uses SYNTHETIC audio (structured sine-wave
"voices" with noise) as a stand-in for real human speech, because no real
labeled voice dataset is bundled with this project. Synthetic tones are a
reasonable way to sanity-check that the pipeline (embedding extraction +
cosine similarity) can separate distinct sources, but the exact FAR/FRR
numbers below are NOT representative of real-world accuracy on human voices.
For genuine accuracy numbers, replace `generate_synthetic_speaker_samples()`
with real recordings of multiple people, each providing several samples.

Usage:
    python scripts/evaluate_voice_accuracy.py
"""
import sys
import os
import wave
from io import BytesIO

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.voice_engine import extract_voice_embedding, cosine_similarity


class _FakeFileStorage:
    """Minimal stand-in for Flask's FileStorage, since extract_voice_embedding
    expects an object with .seek()/.read()."""
    def __init__(self, buf):
        self.buf = buf

    def seek(self, pos):
        self.buf.seek(pos)

    def read(self):
        return self.buf.read()


def _make_wav_bytes(freq, duration=3, sample_rate=16000, seed=0):
    rng = np.random.RandomState(seed)
    t = np.linspace(0, duration, int(sample_rate * duration))
    audio = (
        0.3 * np.sin(2 * np.pi * freq * t)
        + 0.15 * np.sin(2 * np.pi * freq * 2.5 * t)
        + 0.05 * rng.randn(len(t))
    )
    audio = audio / np.max(np.abs(audio))
    audio_int16 = (audio * 32767 * 0.8).astype(np.int16)

    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    buf.seek(0)
    return buf


def load_real_speaker_samples(data_dir):
    """Loads real audio samples from a directory structured as:
        data_dir/
          speaker_1/
            sample1.wav
            sample2.wav
          speaker_2/
            sample1.wav
            ...
    Each subfolder is treated as one speaker; every audio file inside it is
    one sample. Returns {speaker_id: [embedding, ...]} - same shape as
    generate_synthetic_speaker_samples(), so the rest of the script doesn't
    need to know whether the data is real or synthetic.
    """
    speaker_embeddings = {}

    speaker_dirs = sorted(
        d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))
    )

    for speaker_id, speaker_name in enumerate(speaker_dirs):
        speaker_path = os.path.join(data_dir, speaker_name)
        embeddings = []

        for filename in sorted(os.listdir(speaker_path)):
            file_path = os.path.join(speaker_path, filename)
            if not os.path.isfile(file_path):
                continue

            with open(file_path, "rb") as f:
                audio_bytes = BytesIO(f.read())

            embedding = extract_voice_embedding(_FakeFileStorage(audio_bytes))
            if embedding is not None:
                embeddings.append(embedding)
            else:
                print(f"  WARNING: could not extract embedding from {file_path} (too short/invalid), skipping.")

        if embeddings:
            speaker_embeddings[speaker_id] = embeddings
            print(f"  Loaded {len(embeddings)} sample(s) for speaker '{speaker_name}'")

    return speaker_embeddings


def generate_synthetic_speaker_samples(num_speakers=6, samples_per_speaker=4):
    """Generates synthetic 'speakers' as distinct frequency families, each
    with several noisy samples (simulating repeat recordings of the same
    person). Returns {speaker_id: [embedding, embedding, ...]}."""
    base_freqs = np.linspace(100, 320, num_speakers)  # spread across a vocal-pitch-like range

    speaker_embeddings = {}
    seed_counter = 0

    for speaker_id, base_freq in enumerate(base_freqs):
        embeddings = []
        for sample_idx in range(samples_per_speaker):
            # small per-sample frequency jitter simulates natural recording variation
            jitter = base_freq * 0.02 * (sample_idx - samples_per_speaker / 2)
            audio_buf = _make_wav_bytes(base_freq + jitter, seed=seed_counter)
            seed_counter += 1

            embedding = extract_voice_embedding(_FakeFileStorage(audio_buf))
            if embedding is not None:
                embeddings.append(embedding)

        speaker_embeddings[speaker_id] = embeddings

    return speaker_embeddings


def compute_genuine_and_impostor_scores(speaker_embeddings):
    """Returns (genuine_scores, impostor_scores) - cosine similarities for
    same-speaker pairs and different-speaker pairs, respectively."""
    genuine_scores = []
    impostor_scores = []

    speaker_ids = list(speaker_embeddings.keys())

    for speaker_id in speaker_ids:
        embeddings = speaker_embeddings[speaker_id]
        # genuine: all pairs within the same speaker
        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                genuine_scores.append(cosine_similarity(embeddings[i], embeddings[j]))

    for i in range(len(speaker_ids)):
        for j in range(i + 1, len(speaker_ids)):
            embs_a = speaker_embeddings[speaker_ids[i]]
            embs_b = speaker_embeddings[speaker_ids[j]]
            for ea in embs_a:
                for eb in embs_b:
                    impostor_scores.append(cosine_similarity(ea, eb))

    return genuine_scores, impostor_scores


def compute_far_frr(genuine_scores, impostor_scores, threshold):
    """FAR = fraction of impostor pairs incorrectly accepted (score >= threshold)
    FRR = fraction of genuine pairs incorrectly rejected (score < threshold)"""
    far = sum(1 for s in impostor_scores if s >= threshold) / len(impostor_scores)
    frr = sum(1 for s in genuine_scores if s < threshold) / len(genuine_scores)
    return far, frr


def find_equal_error_rate(genuine_scores, impostor_scores, thresholds):
    best_threshold = None
    best_gap = float("inf")
    best_far = best_frr = None

    for t in thresholds:
        far, frr = compute_far_frr(genuine_scores, impostor_scores, t)
        gap = abs(far - frr)
        if gap < best_gap:
            best_gap = gap
            best_threshold = t
            best_far = far
            best_frr = frr

    return best_threshold, best_far, best_frr


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate voice recognition FAR/FRR.")
    parser.add_argument(
        "--real-data-dir",
        type=str,
        default=None,
        help=(
            "Path to a directory of real recordings, structured as "
            "real_data_dir/speaker_name/sample.wav (one subfolder per "
            "speaker, multiple audio files per speaker). If omitted, "
            "synthetic data is used instead (see disclaimer above)."
        ),
    )
    args = parser.parse_args()

    print("=" * 70)
    if args.real_data_dir:
        print("Voice Recognition Evaluation (REAL DATA)")
    else:
        print("Voice Recognition Evaluation (SYNTHETIC DATA - see script header)")
    print("=" * 70)

    if args.real_data_dir:
        print(f"\nLoading real audio samples from {args.real_data_dir}...")
        speaker_embeddings = load_real_speaker_samples(args.real_data_dir)
        if len(speaker_embeddings) < 2:
            print("\nERROR: need at least 2 speakers with valid samples to compute "
                  "impostor pairs. Check your data directory structure.")
            return
    else:
        print("\nGenerating synthetic speaker samples...")
        speaker_embeddings = generate_synthetic_speaker_samples(num_speakers=6, samples_per_speaker=4)

    total_samples = sum(len(v) for v in speaker_embeddings.values())
    source_kind = "real" if args.real_data_dir else "synthetic"
    action = "Loaded" if args.real_data_dir else "Generated"
    print(f"{action} {total_samples} samples across {len(speaker_embeddings)} {source_kind} speakers.")

    print("\nComputing genuine (same-speaker) and impostor (different-speaker) score distributions...")
    genuine_scores, impostor_scores = compute_genuine_and_impostor_scores(speaker_embeddings)
    print(f"Genuine pairs: {len(genuine_scores)}, Impostor pairs: {len(impostor_scores)}")

    print(f"\nGenuine score range:  min={min(genuine_scores):.3f}  max={max(genuine_scores):.3f}  mean={np.mean(genuine_scores):.3f}")
    print(f"Impostor score range: min={min(impostor_scores):.3f}  max={max(impostor_scores):.3f}  mean={np.mean(impostor_scores):.3f}")

    thresholds = np.arange(0.30, 0.99, 0.02)

    print("\nThreshold |   FAR   |   FRR")
    print("-" * 35)
    rows = []
    for t in thresholds:
        far, frr = compute_far_frr(genuine_scores, impostor_scores, t)
        rows.append((round(t, 2), far, frr))
        print(f"  {t:.2f}    | {far:.3f}   | {frr:.3f}")

    eer_threshold, eer_far, eer_frr = find_equal_error_rate(genuine_scores, impostor_scores, thresholds)
    print("\n" + "=" * 70)
    print(f"Equal Error Rate (EER) ~ threshold={eer_threshold:.2f}, FAR={eer_far:.3f}, FRR={eer_frr:.3f}")
    print("=" * 70)

    # Production threshold: intentionally set slightly above the raw EER point
    # (0.58) rather than exactly at it. EER minimizes FAR+FRR jointly, but for
    # attendance a false ACCEPT (marking the wrong/no student present) is a
    # worse failure than a false REJECT (student has to retry recognition).
    # 0.65 trades a bit more FRR for a meaningfully lower FAR than the EER
    # point, while still being far below the old default of 0.75 which had an
    # unacceptably high 33% FRR on this synthetic set. This must be re-tuned
    # once real recorded voice samples are available - see disclaimer above.
    current_threshold = 0.65
    far_at_current, frr_at_current = compute_far_frr(genuine_scores, impostor_scores, current_threshold)
    print(f"\nAt current production threshold ({current_threshold}): FAR={far_at_current:.3f}, FRR={frr_at_current:.3f}")

    # Write results to a markdown file for the README/report
    output_path = os.path.join(os.path.dirname(__file__), "..", "EVALUATION.md")
    with open(output_path, "w") as f:
        f.write("# Voice Recognition Evaluation\n\n")
        if args.real_data_dir:
            f.write(f"**Data source**: real recordings loaded from `{args.real_data_dir}`.\n\n")
        else:
            f.write("**⚠️ Synthetic data disclaimer**: These numbers come from synthetic "
                    "sine-wave \"voices\", not real human speech, because no labeled voice "
                    "dataset was available. They validate that the pipeline (Resemblyzer "
                    "embeddings + cosine similarity) can separate distinct sources, but are "
                    "NOT representative of real-world accuracy. Re-run this script with "
                    "`--real-data-dir <path>` pointing at real recorded voice samples for "
                    "genuine FAR/FRR numbers.\n\n")
        speaker_label = "Real speakers" if args.real_data_dir else "Synthetic speakers"
        f.write(f"- {speaker_label}: {len(speaker_embeddings)}\n")
        f.write(f"- Samples per speaker: {total_samples // len(speaker_embeddings)}\n")
        f.write(f"- Genuine pairs evaluated: {len(genuine_scores)}\n")
        f.write(f"- Impostor pairs evaluated: {len(impostor_scores)}\n\n")
        f.write("## FAR / FRR by threshold\n\n")
        f.write("| Threshold | FAR | FRR |\n|---|---|---|\n")
        for t, far, frr in rows:
            f.write(f"| {t} | {far:.3f} | {frr:.3f} |\n")
        f.write(f"\n## Equal Error Rate\n\nThreshold ≈ **{eer_threshold:.2f}**, FAR = {eer_far:.3f}, FRR = {eer_frr:.3f}\n\n")
        f.write(f"## Current production threshold ({current_threshold})\n\n")
        f.write(f"FAR = {far_at_current:.3f}, FRR = {frr_at_current:.3f}\n\n")
        if args.real_data_dir:
            f.write(
                "**Production-threshold note:** `0.65` is the threshold currently "
                "configured in the application and is reported here for direct "
                "comparison with the real validation set. Do not assume it is "
                "optimal for this dataset; choose a final operating point from "
                "the real FAR/FRR trade-off, giving extra weight to false accepts "
                "for an attendance use case. Revisit it as the dataset grows.\n"
            )
        else:
            f.write(
                "**Why not use the EER threshold directly?** EER minimizes FAR+FRR "
                "jointly, but for an attendance system a false ACCEPT (marking the "
                "wrong or an unenrolled student present) is a worse failure mode "
                "than a false REJECT (the correct student just retries). The "
                "configured threshold is intentionally stricter on this synthetic "
                "sanity-check set. This is not a real-world calibration and must be "
                "revisited with labeled human recordings.\n"
            )

    print(f"\nResults written to {os.path.abspath(output_path)}")


if __name__ == "__main__":
    main()

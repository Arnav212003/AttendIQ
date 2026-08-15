"""
Open-set LBPH face-recognition evaluation.

Computes False Accept Rate (FAR), False Reject Rate (FRR), and an approximate
Equal Error Rate (EER) over a threshold sweep.

Why "open-set" matters for attendance:
- Genuine trial: a held-out photo of an enrolled identity should be accepted
  *and* classified as the correct student.
- Impostor trial: a photo of an identity deliberately left out of training
  should be rejected by the confidence threshold, regardless of which enrolled
  label LBPH predicts for it.

This is more meaningful than treating ordinary multiclass misclassifications
as the only impostor cases; if every synthetic identity classifies correctly,
that older shortcut can misleadingly report FAR=0 without ever testing an
unknown person.

Usage:
    python scripts/evaluate_face_accuracy.py
    python scripts/evaluate_face_accuracy.py --real-data-dir path/to/faces

Real-data directory structure:
    faces/
      person_a/*.jpg
      person_b/*.jpg
      person_c/*.jpg

For useful open-set evaluation, use at least 3 identities and at least 3
photos per identity. Real photos should be face crops because this script
measures the recognizer, not Haar-cascade detection quality.
"""
import argparse
import os
from pathlib import Path

import cv2
import numpy as np


PRODUCTION_THRESHOLD = 90.0


def load_real_identity_patches(data_dir, size=200):
    identity_patches = {}
    dirs = sorted(
        d for d in os.listdir(data_dir)
        if os.path.isdir(os.path.join(data_dir, d))
    )

    for identity_id, identity_name in enumerate(dirs):
        samples = []
        identity_path = os.path.join(data_dir, identity_name)
        for filename in sorted(os.listdir(identity_path)):
            path = os.path.join(identity_path, filename)
            if not os.path.isfile(path):
                continue
            image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if image is None:
                print(f"  WARNING: could not read {path}, skipping.")
                continue
            samples.append(cv2.resize(image, (size, size)))
        if len(samples) >= 3:
            identity_patches[identity_id] = samples
            print(f"  Loaded {len(samples)} samples for identity '{identity_name}'")
        elif samples:
            print(f"  WARNING: identity '{identity_name}' has only {len(samples)} sample(s); need >=3, skipping.")

    return identity_patches


def generate_synthetic_identity_patches(num_identities=8, samples_per_identity=6, size=200):
    """Generate deliberately overlapping texture families.

    Synthetic data is only a pipeline sanity check. Patterns share a common
    base and differ modestly so the task is less trivially separable than the
    previous one-pattern-per-identity setup.
    """
    identity_patches = {}
    xx, yy = np.meshgrid(np.arange(size), np.arange(size))
    shared = 128 + 34 * np.sin(0.055 * xx + 0.037 * yy) + 24 * np.cos(0.043 * xx - 0.051 * yy)

    for identity_id in range(num_identities):
        rng = np.random.RandomState(1000 + identity_id)
        phase = identity_id * 0.28
        identity_component = (
            17 * np.sin(0.071 * xx + 0.046 * yy + phase)
            + 13 * np.cos(0.039 * xx - 0.064 * yy - phase / 2)
        )
        samples = []
        for sample_idx in range(samples_per_identity):
            # Sample-specific illumination/contrast/noise variation.
            brightness = (sample_idx - samples_per_identity / 2) * 2.2
            contrast = 0.94 + 0.025 * sample_idx
            noise = rng.normal(0, 18, size=(size, size))
            patch = np.clip((shared + identity_component + brightness) * contrast + noise, 0, 255).astype(np.uint8)
            samples.append(patch)
        identity_patches[identity_id] = samples
    return identity_patches


def _train_recognizer(training_by_identity):
    faces, labels = [], []
    for identity_id, samples in training_by_identity.items():
        for sample in samples:
            faces.append(sample)
            labels.append(identity_id)
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(faces, np.asarray(labels, dtype=np.int32))
    return recognizer


def collect_open_set_trials(identity_patches):
    """Leave one identity out as unknown in each fold.

    Each fold trains on all other identities. For each enrolled identity, the
    last sample is a genuine test sample and the remaining samples train LBPH.
    Every sample of the held-out identity becomes an impostor/open-set trial.

    Returns:
      genuine_trials: [(confidence, correct_label_bool), ...]
      impostor_confidences: [confidence, ...]
    """
    ids = sorted(identity_patches)
    if len(ids) < 3:
        raise ValueError("Need at least 3 identities for open-set evaluation.")

    genuine_trials = []
    impostor_confidences = []

    for unknown_id in ids:
        training = {}
        genuine_tests = []
        for identity_id in ids:
            samples = identity_patches[identity_id]
            if identity_id == unknown_id:
                continue
            if len(samples) < 3:
                continue
            training[identity_id] = samples[:-1]
            genuine_tests.append((identity_id, samples[-1]))

        if len(training) < 2:
            continue

        recognizer = _train_recognizer(training)

        for true_id, image in genuine_tests:
            predicted_id, confidence = recognizer.predict(image)
            genuine_trials.append((float(confidence), int(predicted_id) == int(true_id)))

        for image in identity_patches[unknown_id]:
            _, confidence = recognizer.predict(image)
            impostor_confidences.append(float(confidence))

    return genuine_trials, impostor_confidences


def compute_far_frr(genuine_trials, impostor_confidences, threshold):
    # LBPH lower confidence = closer match, therefore confidence < threshold
    # means the system accepts the prediction.
    far = (
        sum(conf < threshold for conf in impostor_confidences) / len(impostor_confidences)
        if impostor_confidences else 0.0
    )

    # A genuine user is rejected either when confidence is above threshold OR
    # when LBPH confidently chooses the wrong enrolled identity.
    frr = (
        sum((conf >= threshold) or (not correct) for conf, correct in genuine_trials) / len(genuine_trials)
        if genuine_trials else 0.0
    )
    return far, frr


def find_equal_error_rate(genuine_trials, impostor_confidences, thresholds):
    best = None
    for threshold in thresholds:
        far, frr = compute_far_frr(genuine_trials, impostor_confidences, threshold)
        item = (abs(far - frr), float(threshold), far, frr)
        if best is None or item[0] < best[0]:
            best = item
    _, threshold, far, frr = best
    return threshold, far, frr


def _replace_face_section(output_path, face_markdown):
    path = Path(output_path)
    existing = path.read_text() if path.exists() else ""
    marker = "\n\n---\n\n# Face Recognition Evaluation"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip()
    if existing:
        path.write_text(existing + "\n\n---\n\n" + face_markdown)
    else:
        path.write_text(face_markdown)


def main():
    if not hasattr(cv2, "face"):
        raise SystemExit(
            "OpenCV contrib modules are required for LBPH evaluation. "
            "Install the project requirements (opencv-contrib-python), not plain opencv-python."
        )

    parser = argparse.ArgumentParser(description="Evaluate LBPH face recognition with open-set FAR/FRR.")
    parser.add_argument("--real-data-dir", default=None)
    args = parser.parse_args()

    print("=" * 72)
    print("Face Recognition Evaluation (REAL DATA)" if args.real_data_dir else "Face Recognition Evaluation (SYNTHETIC PIPELINE CHECK)")
    print("=" * 72)

    if args.real_data_dir:
        identity_patches = load_real_identity_patches(args.real_data_dir)
        source_label = "real"
    else:
        identity_patches = generate_synthetic_identity_patches()
        source_label = "synthetic"

    if len(identity_patches) < 3:
        raise SystemExit("Need at least 3 valid identities with >=3 samples each.")

    total_samples = sum(len(samples) for samples in identity_patches.values())
    print(f"Using {len(identity_patches)} {source_label} identities / {total_samples} samples.")

    genuine_trials, impostor_confidences = collect_open_set_trials(identity_patches)
    correct_genuine = sum(correct for _, correct in genuine_trials)
    print(f"Genuine trials: {len(genuine_trials)} (correct-label predictions: {correct_genuine})")
    print(f"Open-set impostor trials: {len(impostor_confidences)}")

    all_conf = [c for c, _ in genuine_trials] + impostor_confidences
    observed_low, observed_high = min(all_conf), max(all_conf)
    low = max(1.0, observed_low - 8)
    high = max(PRODUCTION_THRESHOLD + 10, observed_high + 8)
    thresholds = np.linspace(low, high, 36)

    rows = []
    print("\nThreshold | FAR | FRR")
    print("-" * 30)
    last_pair = None
    repeat_count = 0
    for threshold in thresholds:
        far, frr = compute_far_frr(genuine_trials, impostor_confidences, threshold)
        rows.append((round(float(threshold), 1), far, frr))

        # Once FAR/FRR stop changing (we've swept past the observed confidence
        # range), printing every remaining row is just noise - show a couple
        # for confirmation then collapse the rest into a summary line.
        current_pair = (round(far, 3), round(frr, 3))
        if current_pair == last_pair:
            repeat_count += 1
            if repeat_count <= 2:
                print(f"{threshold:8.1f} | {far:.3f} | {frr:.3f}")
            elif repeat_count == 3:
                print("     ...   |  (unchanged for remaining thresholds - see note below)")
        else:
            repeat_count = 0
            print(f"{threshold:8.1f} | {far:.3f} | {frr:.3f}")
        last_pair = current_pair

    eer_t, eer_far, eer_frr = find_equal_error_rate(genuine_trials, impostor_confidences, thresholds)
    prod_far, prod_frr = compute_far_frr(genuine_trials, impostor_confidences, PRODUCTION_THRESHOLD)
    print(f"\nObserved confidence range: {observed_low:.1f} - {observed_high:.1f}")
    print(f"Approx EER point: threshold={eer_t:.1f}, FAR={eer_far:.3f}, FRR={eer_frr:.3f}")
    print(f"Production threshold {PRODUCTION_THRESHOLD:.0f}: FAR={prod_far:.3f}, FRR={prod_frr:.3f}")

    threshold_out_of_range = PRODUCTION_THRESHOLD > observed_high + 1
    if threshold_out_of_range:
        print(
            f"\nWARNING: production threshold ({PRODUCTION_THRESHOLD:.0f}) is far outside the "
            f"observed confidence range ({observed_low:.1f}-{observed_high:.1f}) on this dataset. "
            "At this threshold, essentially every trial's confidence gate is a no-op (nothing gets "
            "rejected by confidence alone) - FAR/FRR at this threshold mostly reflect the recognizer's "
            "raw label-matching behavior, not real threshold-based discrimination. This is a sign the "
            "threshold should be re-tuned closer to the observed range, not evidence the threshold "
            "itself is being meaningfully exercised."
        )

    lines = ["# Face Recognition Evaluation", ""]
    if args.real_data_dir:
        lines += [
            f"**Data source:** real cropped face photos from `{args.real_data_dir}`.",
            "",
            "This is an **open-set** evaluation: each fold leaves one identity completely out of training and uses that person's photos as impostor trials.",
            "",
        ]
    else:
        lines += [
            "**⚠️ Synthetic pipeline-check disclaimer:** these results use generated texture patches, not human face photos. They validate the evaluation/code path but are **not real-world biometric accuracy**.",
            "",
            "Unlike the older report, this version uses an **open-set** protocol: one synthetic identity is left out of training in each fold and treated as an unknown/impostor identity. That makes FAR meaningful as a pipeline metric instead of defining impostors only as ordinary multiclass mistakes.",
            "",
        ]

    lines += [
        f"- {'Real' if args.real_data_dir else 'Synthetic'} identities: {len(identity_patches)}",
        f"- Total samples: {total_samples}",
        f"- Genuine trials: {len(genuine_trials)}",
        f"- Open-set impostor trials: {len(impostor_confidences)}",
        f"- Genuine trials with correct predicted identity: {correct_genuine}",
        "",
        "## FAR / FRR by threshold",
        "",
        "| Threshold | FAR | FRR |",
        "|---|---|---|",
    ]
    lines += [f"| {t} | {far:.3f} | {frr:.3f} |" for t, far, frr in rows]
    lines += [
        "",
        "## Approximate Equal Error Rate",
        "",
        f"Threshold ≈ **{eer_t:.1f}**, FAR = {eer_far:.3f}, FRR = {eer_frr:.3f}",
        "",
        f"## Current production threshold ({PRODUCTION_THRESHOLD:.0f})",
        "",
        f"Observed confidence range on this dataset: {observed_low:.1f} - {observed_high:.1f}",
        "",
        f"FAR = {prod_far:.3f}, FRR = {prod_frr:.3f}",
        "",
    ]
    if threshold_out_of_range:
        lines += [
            f"**⚠️ Threshold out of range**: the production threshold ({PRODUCTION_THRESHOLD:.0f}) is far "
            f"outside the observed confidence range above. At this threshold the confidence gate is "
            f"essentially a no-op - nothing gets rejected by confidence alone - so the FAR/FRR numbers "
            f"above mostly reflect raw label-matching behavior, not meaningful threshold-based "
            f"discrimination. This indicates the threshold should be re-tuned closer to the observed "
            f"range rather than being read as a working production setting.",
            "",
        ]
    lines += [
        "The production threshold must be re-tuned on labeled human face data before making any real-world accuracy claim." if not args.real_data_dir else "Re-tune the production threshold as the real validation set grows and becomes more representative.",
        "",
    ]

    output_path = Path(__file__).resolve().parent.parent / "EVALUATION.md"
    _replace_face_section(output_path, "\n".join(lines))
    print(f"\nFace results written to {output_path}")


if __name__ == "__main__":
    main()

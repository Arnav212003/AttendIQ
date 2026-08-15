# Voice Recognition Evaluation

**⚠️ Synthetic data disclaimer**: These numbers come from synthetic sine-wave "voices", not real human speech, because no labeled voice dataset was available. They validate that the pipeline (Resemblyzer embeddings + cosine similarity) can separate distinct sources, but are NOT representative of real-world accuracy. Re-run this script with `--real-data-dir <path>` pointing at real recorded voice samples for genuine FAR/FRR numbers.

- Synthetic speakers: 6
- Samples per speaker: 4
- Genuine pairs evaluated: 36
- Impostor pairs evaluated: 240

## FAR / FRR by threshold

| Threshold | FAR | FRR |
|---|---|---|
| 0.3 | 1.000 | 0.000 |
| 0.32 | 0.996 | 0.000 |
| 0.34 | 0.979 | 0.000 |
| 0.36 | 0.954 | 0.000 |
| 0.38 | 0.896 | 0.000 |
| 0.4 | 0.792 | 0.000 |
| 0.42 | 0.704 | 0.000 |
| 0.44 | 0.642 | 0.000 |
| 0.46 | 0.546 | 0.000 |
| 0.48 | 0.458 | 0.000 |
| 0.5 | 0.312 | 0.000 |
| 0.52 | 0.242 | 0.056 |
| 0.54 | 0.150 | 0.056 |
| 0.56 | 0.108 | 0.056 |
| 0.58 | 0.083 | 0.083 |
| 0.6 | 0.071 | 0.083 |
| 0.62 | 0.067 | 0.083 |
| 0.64 | 0.046 | 0.167 |
| 0.66 | 0.046 | 0.194 |
| 0.68 | 0.037 | 0.194 |
| 0.7 | 0.025 | 0.222 |
| 0.72 | 0.017 | 0.306 |
| 0.74 | 0.008 | 0.333 |
| 0.76 | 0.000 | 0.333 |
| 0.78 | 0.000 | 0.389 |
| 0.8 | 0.000 | 0.389 |
| 0.82 | 0.000 | 0.417 |
| 0.84 | 0.000 | 0.472 |
| 0.86 | 0.000 | 0.556 |
| 0.88 | 0.000 | 0.611 |
| 0.9 | 0.000 | 0.639 |
| 0.92 | 0.000 | 0.722 |
| 0.94 | 0.000 | 0.833 |
| 0.96 | 0.000 | 0.889 |
| 0.98 | 0.000 | 0.972 |

## Equal Error Rate

Threshold ≈ **0.58**, FAR = 0.083, FRR = 0.083

## Current production threshold (0.65)

FAR = 0.046, FRR = 0.167

**Why not use the EER threshold directly?** EER minimizes FAR+FRR jointly, but for an attendance system a false ACCEPT (marking the wrong or an unenrolled student present) is a worse failure mode than a false REJECT (the correct student just retries). The production threshold is set moderately above the EER point to bias toward fewer false accepts, at the cost of a higher false-reject rate. This is a synthetic-data judgment call and should be revisited once real voice samples are available.

---

# Face Recognition Evaluation

**⚠️ Synthetic pipeline-check disclaimer:** these results use generated texture patches, not human face photos. They validate the evaluation/code path but are **not real-world biometric accuracy**.

Unlike the older report, this version uses an **open-set** protocol: one synthetic identity is left out of training in each fold and treated as an unknown/impostor identity. That makes FAR meaningful as a pipeline metric instead of defining impostors only as ordinary multiclass mistakes.

- Synthetic identities: 8
- Total samples: 48
- Genuine trials: 56
- Open-set impostor trials: 48
- Genuine trials with correct predicted identity: 11

## FAR / FRR by threshold

| Threshold | FAR | FRR |
|---|---|---|
| 32.7 | 0.000 | 1.000 |
| 34.7 | 0.000 | 1.000 |
| 36.6 | 0.000 | 1.000 |
| 38.5 | 0.000 | 1.000 |
| 40.4 | 0.000 | 1.000 |
| 42.3 | 1.000 | 0.804 |
| 44.3 | 1.000 | 0.804 |
| 46.2 | 1.000 | 0.804 |
| 48.1 | 1.000 | 0.804 |
| 50.0 | 1.000 | 0.804 |
| 52.0 | 1.000 | 0.804 |
| 53.9 | 1.000 | 0.804 |
| 55.8 | 1.000 | 0.804 |
| 57.7 | 1.000 | 0.804 |
| 59.6 | 1.000 | 0.804 |
| 61.6 | 1.000 | 0.804 |
| 63.5 | 1.000 | 0.804 |
| 65.4 | 1.000 | 0.804 |
| 67.3 | 1.000 | 0.804 |
| 69.2 | 1.000 | 0.804 |
| 71.2 | 1.000 | 0.804 |
| 73.1 | 1.000 | 0.804 |
| 75.0 | 1.000 | 0.804 |
| 76.9 | 1.000 | 0.804 |
| 78.9 | 1.000 | 0.804 |
| 80.8 | 1.000 | 0.804 |
| 82.7 | 1.000 | 0.804 |
| 84.6 | 1.000 | 0.804 |
| 86.5 | 1.000 | 0.804 |
| 88.5 | 1.000 | 0.804 |
| 90.4 | 1.000 | 0.804 |
| 92.3 | 1.000 | 0.804 |
| 94.2 | 1.000 | 0.804 |
| 96.2 | 1.000 | 0.804 |
| 98.1 | 1.000 | 0.804 |
| 100.0 | 1.000 | 0.804 |

## Approximate Equal Error Rate

Threshold ≈ **42.3**, FAR = 1.000, FRR = 0.804

## Current production threshold (90)

Observed confidence range on this dataset: 40.7 - 41.8

FAR = 1.000, FRR = 0.804

**⚠️ Threshold out of range**: the production threshold (90) is far outside the observed confidence range above. At this threshold the confidence gate is essentially a no-op - nothing gets rejected by confidence alone - so the FAR/FRR numbers above mostly reflect raw label-matching behavior, not meaningful threshold-based discrimination. This indicates the threshold should be re-tuned closer to the observed range rather than being read as a working production setting.

The production threshold must be re-tuned on labeled human face data before making any real-world accuracy claim.

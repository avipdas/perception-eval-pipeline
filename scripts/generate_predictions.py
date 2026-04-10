"""Generate synthetic predictions from ground truths for pipeline testing.

Creates realistic-looking predictions by adding controlled noise to the
ground truth boxes.  This lets you test the full evaluation pipeline
without needing actual model outputs.

Noise model
-----------
- Position noise scales with distance (farther objects are harder to detect)
- Some objects are randomly missed  (simulates false negatives)
- Hallucinated detections are added  (simulates false positives)
- Confidence correlates inversely with noise magnitude

Usage:
    python -m scripts.generate_predictions
    python -m scripts.generate_predictions --miss-rate 0.2 --noise 0.5
    python -m scripts.generate_predictions --clear   # wipe old predictions first
"""

from __future__ import annotations

import argparse
import math
import random

from storage.database import DatabaseManager
from storage.schema import Frame, GroundTruth, Prediction


FRAME_PROFILES = [
    {"miss_rate": 0.02, "hallucination_rate": 0.02, "noise": 0.05, "label": "excellent"},
    {"miss_rate": 0.05, "hallucination_rate": 0.05, "noise": 0.10, "label": "good"},
    {"miss_rate": 0.10, "hallucination_rate": 0.08, "noise": 0.18, "label": "decent"},
    {"miss_rate": 0.25, "hallucination_rate": 0.05, "noise": 0.12, "label": "miss-heavy"},
    {"miss_rate": 0.40, "hallucination_rate": 0.03, "noise": 0.10, "label": "many-misses"},
    {"miss_rate": 0.05, "hallucination_rate": 0.30, "noise": 0.08, "label": "halluc-heavy"},
    {"miss_rate": 0.08, "hallucination_rate": 0.15, "noise": 0.25, "label": "noisy"},
    {"miss_rate": 0.15, "hallucination_rate": 0.12, "noise": 0.20, "label": "mixed"},
    {"miss_rate": 0.50, "hallucination_rate": 0.40, "noise": 0.35, "label": "terrible"},
]


def _generate_for_frame(
    session,
    frame: Frame,
    miss_rate: float,
    hallucination_rate: float,
    noise_scale: float,
) -> int:
    """Create noisy predictions for every GT in *frame*. Returns count."""
    gts = (
        session.query(GroundTruth)
        .filter(GroundTruth.frame_id == frame.id)
        .all()
    )
    count = 0

    for gt in gts:
        if random.random() < miss_rate:
            continue

        distance_factor = 1.0 + (gt.range / 100.0)

        nx = random.gauss(0, noise_scale * distance_factor)
        ny = random.gauss(0, noise_scale * distance_factor)
        nz = random.gauss(0, noise_scale * 0.2)
        nl = random.gauss(0, noise_scale * 0.15)
        nw = random.gauss(0, noise_scale * 0.15)
        nh = random.gauss(0, noise_scale * 0.08)
        n_heading = random.gauss(0, 0.05 * distance_factor * (noise_scale / 0.3))

        pred_cx = gt.center_x + nx
        pred_cy = gt.center_y + ny
        pred_cz = gt.center_z + nz
        pred_l = max(0.5, gt.length + nl)
        pred_w = max(0.3, gt.width + nw)
        pred_h = max(0.3, gt.height + nh)
        pred_heading = gt.heading + n_heading

        noise_mag = math.sqrt(nx ** 2 + ny ** 2)
        confidence = max(0.1, min(0.99, 0.92 - noise_mag * 0.1 - gt.range / 300.0))

        session.add(
            Prediction(
                frame_id=frame.id,
                object_type=gt.object_type,
                confidence=round(confidence, 4),
                center_x=round(pred_cx, 4),
                center_y=round(pred_cy, 4),
                center_z=round(pred_cz, 4),
                length=round(pred_l, 4),
                width=round(pred_w, 4),
                height=round(pred_h, 4),
                heading=round(pred_heading, 4),
                range=round(math.sqrt(pred_cx ** 2 + pred_cy ** 2), 4),
            )
        )
        count += 1

    num_fp = max(0, int(len(gts) * hallucination_rate))
    for _ in range(num_fp):
        angle = random.uniform(0, 2 * math.pi)
        dist = random.uniform(10, 80)
        cx = dist * math.cos(angle)
        cy = dist * math.sin(angle)

        session.add(
            Prediction(
                frame_id=frame.id,
                object_type=random.choice([1, 2, 4]),
                confidence=round(random.uniform(0.05, 0.45), 4),
                center_x=round(cx, 4),
                center_y=round(cy, 4),
                center_z=round(random.uniform(-1, 1), 4),
                length=round(random.uniform(1.0, 5.0), 4),
                width=round(random.uniform(0.5, 2.5), 4),
                height=round(random.uniform(1.0, 2.5), 4),
                heading=round(random.uniform(-math.pi, math.pi), 4),
                range=round(dist, 4),
            )
        )
        count += 1

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic predictions.")
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--clear", action="store_true",
        help="Delete all existing predictions before generating.",
    )
    args = parser.parse_args()

    random.seed(args.seed)
    db = DatabaseManager()
    db.create_tables()

    with db.session() as session:
        if args.clear:
            deleted = session.query(Prediction).delete()
            print(f"Cleared {deleted} existing predictions.")

        frames = session.query(Frame).order_by(Frame.id).all()
        if not frames:
            print("No frames in database. Run ingestion first:")
            print("  python -m ingestion.ingest")
            return

        shuffled_profiles = list(FRAME_PROFILES)
        random.shuffle(shuffled_profiles)

        total = 0
        for i, frame in enumerate(frames):
            profile = shuffled_profiles[i % len(shuffled_profiles)]
            n = _generate_for_frame(
                session, frame,
                miss_rate=profile["miss_rate"],
                hallucination_rate=profile["hallucination_rate"],
                noise_scale=profile["noise"],
            )
            total += n
            print(f"  Frame {frame.id:>3} [{profile['label']:>13}]  "
                  f"miss={profile['miss_rate']:.0%}  halluc={profile['hallucination_rate']:.0%}  "
                  f"noise={profile['noise']:.2f}  → {n} preds")

    print(f"\nGenerated {total} synthetic predictions across {len(frames)} frames.")


if __name__ == "__main__":
    main()

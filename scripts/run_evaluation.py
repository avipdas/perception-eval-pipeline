"""Run the full evaluation loop.

Reads ground truths and predictions from the database, runs matching,
computes all metrics (AP, APH, IoU, SDE), and stores every per-detection
result back into the eval_results table for downstream SQL slicing.

Usage:
    python -m scripts.run_evaluation
    python -m scripts.run_evaluation --run-name baseline_v1
"""

from __future__ import annotations

import argparse
from collections import defaultdict

import numpy as np

from evaluation.matching import match_frame
from evaluation.metrics import compute_ap, compute_aph
from evaluation.sde import compute_sde, compute_signed_sde
from storage.database import DatabaseManager
from storage.schema import EvalResult, Frame, GroundTruth, Prediction

TYPE_NAMES = {1: "VEHICLE", 2: "PEDESTRIAN", 3: "SIGN", 4: "CYCLIST"}
EVAL_TYPES = [1, 2, 4]  # skip SIGN for standard Waymo eval


def _gt_to_dict(gt: GroundTruth) -> dict:
    return {
        "db_id": gt.id,
        "id": gt.object_id,
        "type": gt.object_type,
        "center_x": gt.center_x,
        "center_y": gt.center_y,
        "center_z": gt.center_z,
        "length": gt.length,
        "width": gt.width,
        "height": gt.height,
        "heading": gt.heading,
        "range": gt.range,
    }


def _pred_to_dict(pred: Prediction) -> dict:
    return {
        "db_id": pred.id,
        "id": f"pred_{pred.id}",
        "type": pred.object_type,
        "center_x": pred.center_x,
        "center_y": pred.center_y,
        "center_z": pred.center_z,
        "length": pred.length,
        "width": pred.width,
        "height": pred.height,
        "heading": pred.heading,
        "confidence": pred.confidence,
        "range": pred.range,
    }


def _evaluate_all(db: DatabaseManager, run_name: str) -> None:
    pooled: dict[int, dict] = {
        t: {"matches": [], "num_gt": 0} for t in EVAL_TYPES
    }
    all_sde: dict[int, list[float]] = defaultdict(list)

    with db.session() as session:
        session.query(EvalResult).filter(EvalResult.run_name == run_name).delete()

        frames = session.query(Frame).all()
        if not frames:
            print("No frames in database. Run ingestion first.")
            return

        num_preds = session.query(Prediction).count()
        if num_preds == 0:
            print("No predictions in database. Generate or ingest predictions first:")
            print("  python -m scripts.generate_predictions")
            return

        print(f"Evaluating {len(frames)} frames, {num_preds} predictions "
              f"(run: '{run_name}') ...")

        for frame in frames:
            gt_rows = (
                session.query(GroundTruth)
                .filter(GroundTruth.frame_id == frame.id)
                .all()
            )
            pred_rows = (
                session.query(Prediction)
                .filter(Prediction.frame_id == frame.id)
                .all()
            )

            gt_dicts = [_gt_to_dict(g) for g in gt_rows]
            pred_dicts = [_pred_to_dict(p) for p in pred_rows]

            gt_by_id: dict[str, dict] = {g["id"]: g for g in gt_dicts}
            pred_by_dbid: dict[int, dict] = {p["db_id"]: p for p in pred_dicts}

            for obj_type in EVAL_TYPES:
                type_gts = [g for g in gt_dicts if g["type"] == obj_type]
                type_preds = [p for p in pred_dicts if p["type"] == obj_type]

                matches = match_frame(type_gts, type_preds, obj_type)
                pooled[obj_type]["matches"].extend(matches)
                pooled[obj_type]["num_gt"] += len(type_gts)

                for m in matches:
                    sde_val = None
                    signed_sde_val = None
                    gt_range = None
                    gt_db_id = m.get("gt_db_id")
                    pred_db_id = m.get("pred_db_id")

                    if m["match_type"] == "TP":
                        gt_dict = gt_by_id.get(m["gt_id"])
                        pred_dict = pred_by_dbid.get(pred_db_id) if pred_db_id else None
                        if gt_dict:
                            gt_range = gt_dict["range"]
                            gt_db_id = gt_dict["db_id"]
                        if gt_dict and pred_dict:
                            sde_val = round(compute_sde(gt_dict, pred_dict), 6)
                            signed_sde_val = round(
                                compute_signed_sde(gt_dict, pred_dict), 6,
                            )
                            all_sde[obj_type].append(sde_val)

                    elif m["match_type"] == "FN":
                        gt_dict = gt_by_id.get(m["gt_id"])
                        if gt_dict:
                            gt_db_id = gt_dict["db_id"]
                            gt_range = gt_dict["range"]

                    session.add(
                        EvalResult(
                            run_name=run_name,
                            frame_id=frame.id,
                            object_type=obj_type,
                            match_type=m["match_type"],
                            prediction_id=pred_db_id,
                            ground_truth_id=gt_db_id,
                            confidence=m.get("confidence"),
                            iou=m.get("iou"),
                            heading_accuracy=m.get("heading_accuracy"),
                            sde=sde_val,
                            signed_sde=signed_sde_val,
                            gt_range=gt_range,
                        )
                    )

    _print_summary(pooled, all_sde)


def _print_summary(
    pooled: dict[int, dict],
    all_sde: dict[int, list[float]],
) -> None:
    print()
    print("=" * 64)
    print(f"{'Type':<14} {'AP':>8} {'APH':>8} {'Mean SDE':>10} {'#GT':>8}")
    print("-" * 64)

    aps: list[float] = []
    aphs: list[float] = []

    for obj_type in EVAL_TYPES:
        p = pooled[obj_type]
        ap = compute_ap(p["matches"], p["num_gt"])
        aph = compute_aph(p["matches"], p["num_gt"])
        sde_vals = all_sde.get(obj_type, [])
        mean_sde = float(np.mean(sde_vals)) if sde_vals else float("nan")

        name = TYPE_NAMES[obj_type]
        print(f"{name:<14} {ap:>8.4f} {aph:>8.4f} {mean_sde:>10.4f} {p['num_gt']:>8}")

        if p["num_gt"] > 0:
            aps.append(ap)
            aphs.append(aph)

    print("-" * 64)

    m_ap = float(np.mean(aps)) if aps else 0.0
    m_aph = float(np.mean(aphs)) if aphs else 0.0
    flat_sde = [v for vals in all_sde.values() for v in vals]
    overall_sde = float(np.mean(flat_sde)) if flat_sde else float("nan")

    print(f"{'OVERALL':<14} {m_ap:>8.4f} {m_aph:>8.4f} {overall_sde:>10.4f}")
    print("=" * 64)
    print("\nResults saved to eval_results table.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run perception evaluation.")
    parser.add_argument(
        "--run-name", default="default",
        help="Name for this evaluation run (default: 'default')",
    )
    args = parser.parse_args()

    db = DatabaseManager()
    db.create_tables()
    _evaluate_all(db, args.run_name)


if __name__ == "__main__":
    main()

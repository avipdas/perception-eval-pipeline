"""Compute AP (Average Precision) and APH (AP with Heading).

AP: area under the precision-recall curve.
APH: same curve, but every TP's precision contribution is weighted
     by its heading accuracy. This penalises detections that found
     the object but got the direction wrong — critical because
     downstream trajectory prediction needs correct heading.

mAP: the mean of AP across all object types.
"""

import numpy as np

from evaluation.matching import match_frame, IOU_THRESHOLDS


def compute_ap(matches: list[dict], num_gt: int) -> float:
    """Compute Average Precision from a list of TP/FP matches.

    Parameters
    ----------
    matches : list of dicts with "match_type" and "confidence"
              (only TPs and FPs — FNs are excluded but counted via num_gt)
    num_gt : total number of ground truths

    Returns
    -------
    AP as a float in [0, 1].
    """
    if num_gt == 0:
        return 0.0

    # Sort by confidence descending
    tp_fp = [m for m in matches if m["match_type"] in ("TP", "FP")]
    tp_fp.sort(key=lambda m: m["confidence"], reverse=True)

    tp_cumsum = 0
    fp_cumsum = 0
    precisions = []
    recalls = []

    for m in tp_fp:
        if m["match_type"] == "TP":
            tp_cumsum += 1
        else:
            fp_cumsum += 1

        precision = tp_cumsum / (tp_cumsum + fp_cumsum)
        recall = tp_cumsum / num_gt

        precisions.append(precision)
        recalls.append(recall)

    if not precisions:
        return 0.0

    # Standard 101-point interpolation (same method as COCO/Waymo)
    precisions = np.array(precisions)
    recalls = np.array(recalls)

    # Make precision monotonically decreasing (right-to-left max)
    for i in range(len(precisions) - 2, -1, -1):
        precisions[i] = max(precisions[i], precisions[i + 1])

    # Sample at 101 evenly spaced recall points
    recall_points = np.linspace(0, 1, 101)
    interpolated = np.zeros_like(recall_points)

    for i, r in enumerate(recall_points):
        # Find precision at the smallest recall >= r
        mask = recalls >= r
        if mask.any():
            interpolated[i] = precisions[mask][0]

    return float(np.mean(interpolated))


def compute_aph(matches: list[dict], num_gt: int) -> float:
    """Compute Average Precision with Heading (APH).

    Same as AP, but each TP counts as heading_accuracy instead of 1.
    A detection that found the car but got the heading 90 degrees wrong
    only counts as a partial TP. This is critical because if you tell
    the planner a car is facing the wrong direction, the predicted
    trajectory will be completely wrong.
    """
    if num_gt == 0:
        return 0.0

    tp_fp = [m for m in matches if m["match_type"] in ("TP", "FP")]
    tp_fp.sort(key=lambda m: m["confidence"], reverse=True)

    # Instead of counting each TP as 1, count it as heading_accuracy
    weighted_tp_cumsum = 0.0
    total_cumsum = 0
    precisions = []
    recalls = []

    for m in tp_fp:
        total_cumsum += 1
        if m["match_type"] == "TP":
            weighted_tp_cumsum += m["heading_accuracy"]

        precision = weighted_tp_cumsum / total_cumsum
        recall = weighted_tp_cumsum / num_gt

        precisions.append(precision)
        recalls.append(recall)

    if not precisions:
        return 0.0

    precisions = np.array(precisions)
    recalls = np.array(recalls)

    for i in range(len(precisions) - 2, -1, -1):
        precisions[i] = max(precisions[i], precisions[i + 1])

    recall_points = np.linspace(0, 1, 101)
    interpolated = np.zeros_like(recall_points)

    for i, r in enumerate(recall_points):
        mask = recalls >= r
        if mask.any():
            interpolated[i] = precisions[mask][0]

    return float(np.mean(interpolated))


def evaluate_frame(ground_truths: list[dict], predictions: list[dict]) -> dict:
    """Run full evaluation on one frame. Returns AP and APH per object type."""
    results = {}

    for obj_type, type_name in [(1, "VEHICLE"), (2, "PEDESTRIAN"), (4, "CYCLIST")]:
        gts = [g for g in ground_truths if g["type"] == obj_type]
        preds = [p for p in predictions if p["type"] == obj_type]

        matches = match_frame(gts, preds, obj_type)
        ap = compute_ap(matches, num_gt=len(gts))
        aph = compute_aph(matches, num_gt=len(gts))

        results[type_name] = {"AP": ap, "APH": aph, "num_gt": len(gts), "matches": matches}

    return results


def compute_map(per_frame_results: list[dict]) -> dict:
    """Compute mAP and mAPH across multiple frames.

    Parameters
    ----------
    per_frame_results : list of dicts returned by evaluate_frame()

    Returns
    -------
    Dict with mAP, mAPH, and per-type breakdowns.
    """
    type_names = ["VEHICLE", "PEDESTRIAN", "CYCLIST"]

    # Pool all matches across frames, per type
    pooled = {t: {"matches": [], "num_gt": 0} for t in type_names}
    for frame_result in per_frame_results:
        for t in type_names:
            if t in frame_result:
                pooled[t]["matches"].extend(frame_result[t]["matches"])
                pooled[t]["num_gt"] += frame_result[t]["num_gt"]

    breakdown = {}
    for t in type_names:
        ap = compute_ap(pooled[t]["matches"], pooled[t]["num_gt"])
        aph = compute_aph(pooled[t]["matches"], pooled[t]["num_gt"])
        breakdown[t] = {"AP": ap, "APH": aph, "num_gt": pooled[t]["num_gt"]}

    aps = [breakdown[t]["AP"] for t in type_names if breakdown[t]["num_gt"] > 0]
    aphs = [breakdown[t]["APH"] for t in type_names if breakdown[t]["num_gt"] > 0]

    return {
        "mAP": float(np.mean(aps)) if aps else 0.0,
        "mAPH": float(np.mean(aphs)) if aphs else 0.0,
        "per_type": breakdown,
    }

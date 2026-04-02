"""Match predictions to ground truths using IoU.

For each frame, this produces a list of matches categorised as:
- TP (True Positive): prediction matched a ground truth above the IoU threshold
- FP (False Positive): prediction didn't match anything
- FN (False Negative): ground truth that no prediction matched (a miss)

The matching is greedy: predictions are processed in descending confidence
order. Each prediction is matched to the highest-IoU unmatched ground truth.
This is the standard approach used by COCO and Waymo (TYPE_SCORE_FIRST).
"""

from evaluation.iou import iou_3d

# Waymo's official IoU thresholds per object type
IOU_THRESHOLDS = {
    1: 0.7,   # VEHICLE
    2: 0.5,   # PEDESTRIAN
    3: 0.5,   # SIGN
    4: 0.5,   # CYCLIST
}


def match_frame(ground_truths: list[dict], predictions: list[dict], object_type: int) -> list[dict]:
    """Match predictions to ground truths for a single object type in one frame.

    Parameters
    ----------
    ground_truths : list of dicts with box keys + "id"
    predictions : list of dicts with box keys + "confidence"
    object_type : int (1=VEHICLE, 2=PED, 3=SIGN, 4=CYCLIST)

    Returns
    -------
    List of match dicts, each with:
        match_type: "TP", "FP", or "FN"
        confidence: prediction confidence (None for FN)
        iou: IoU value (None for FP/FN)
        gt_id: ground truth object_id (None for FP)
        heading_accuracy: cosine similarity of headings (None for FP/FN)
    """
    import math

    iou_threshold = IOU_THRESHOLDS.get(object_type, 0.5)

    # Sort predictions by confidence, highest first
    preds_sorted = sorted(predictions, key=lambda p: p["confidence"], reverse=True)

    # Track which ground truths have been claimed
    matched_gt_ids = set()
    results = []

    for pred in preds_sorted:
        best_iou = 0.0
        best_gt = None

        for gt in ground_truths:
            if gt["id"] in matched_gt_ids:
                continue

            score = iou_3d(pred, gt)
            if score > best_iou:
                best_iou = score
                best_gt = gt

        if best_gt is not None and best_iou >= iou_threshold:
            matched_gt_ids.add(best_gt["id"])

            heading_diff = pred["heading"] - best_gt["heading"]
            heading_accuracy = abs(math.cos(heading_diff))

            results.append({
                "match_type": "TP",
                "confidence": pred["confidence"],
                "iou": best_iou,
                "gt_id": best_gt["id"],
                "gt_db_id": best_gt.get("db_id"),
                "pred_db_id": pred.get("db_id"),
                "heading_accuracy": heading_accuracy,
            })
        else:
            results.append({
                "match_type": "FP",
                "confidence": pred["confidence"],
                "iou": None,
                "gt_id": None,
                "gt_db_id": None,
                "pred_db_id": pred.get("db_id"),
                "heading_accuracy": None,
            })

    for gt in ground_truths:
        if gt["id"] not in matched_gt_ids:
            results.append({
                "match_type": "FN",
                "confidence": None,
                "iou": None,
                "gt_id": gt["id"],
                "gt_db_id": gt.get("db_id"),
                "pred_db_id": None,
                "heading_accuracy": None,
            })

    return results

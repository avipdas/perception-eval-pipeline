"""FastAPI backend for the 3D visualization dashboard.

Serves LiDAR point clouds, bounding boxes, and evaluation results
to the React frontend.

    cd dashboard
    uvicorn api:app --reload --port 8000
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is on the path so storage/analysis imports work
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import text

from dashboard.point_cloud import (
    extract_front_camera,
    extract_point_cloud,
    find_tfrecord_for_context,
    load_frame_from_tfrecord,
)
from storage.database import DatabaseManager
from storage.schema import EvalResult, Frame, GroundTruth, Prediction, Segment

_DATA_DIR       = _PROJECT_ROOT / "data"
_RAW_WAYMO_DIR  = _DATA_DIR / "raw" / "waymo"
_TRIAGE_JSONL   = _DATA_DIR / "processed" / "triage_results.jsonl"

app = FastAPI(title="Perception Eval Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _db() -> DatabaseManager:
    db_path = _PROJECT_ROOT / "data" / "eval.db"
    return DatabaseManager(f"sqlite:///{db_path}")


# ── GET /api/frames ──────────────────────────────────────────────────

@app.get("/api/frames")
def list_frames():
    """Return every frame with its segment metadata."""
    db = _db()
    with db.session() as s:
        rows = (
            s.query(Frame, Segment)
            .join(Segment, Frame.segment_id == Segment.id)
            .order_by(Frame.id)
            .all()
        )
        return [
            {
                "id": f.id,
                "frame_index": f.frame_index,
                "timestamp_micros": f.timestamp_micros,
                "segment_id": f.segment_id,
                "context_name": seg.context_name,
                "location": seg.location,
                "weather": seg.weather,
                "time_of_day": seg.time_of_day,
            }
            for f, seg in rows
        ]


# ── GET /api/frames/{id}/point_cloud ─────────────────────────────────

@app.get("/api/frames/{frame_id}/point_cloud")
def get_point_cloud(frame_id: int):
    """Return a binary Float32 buffer of (x, y, z, intensity) × N."""
    db = _db()
    with db.session() as s:
        frame = s.query(Frame).filter(Frame.id == frame_id).first()
        if frame is None:
            raise HTTPException(404, "Frame not found")
        seg = s.query(Segment).filter(Segment.id == frame.segment_id).first()
        context_name = seg.context_name
        frame_index = frame.frame_index

    tfrecord = find_tfrecord_for_context(context_name, data_dir=_RAW_WAYMO_DIR)
    if tfrecord is None:
        raise HTTPException(
            404, f"TFRecord for context {context_name} not found in {_RAW_WAYMO_DIR}",
        )

    proto_frame = load_frame_from_tfrecord(tfrecord, frame_index)
    cloud = extract_point_cloud(proto_frame)

    return Response(
        content=cloud.tobytes(),
        media_type="application/octet-stream",
        headers={
            "X-Point-Count": str(cloud.shape[0]),
            "X-Channels": "4",
        },
    )


# ── GET /api/frames/{id}/boxes ───────────────────────────────────────

@app.get("/api/frames/{frame_id}/boxes")
def get_boxes(frame_id: int, run_name: str = "waymo_v1"):
    """Return GT and prediction boxes enriched with eval results."""
    db = _db()
    boxes: list[dict] = []

    with db.session() as s:
        frame = s.query(Frame).filter(Frame.id == frame_id).first()
        if frame is None:
            raise HTTPException(404, "Frame not found")

        # Ground truths
        gts = s.query(GroundTruth).filter(GroundTruth.frame_id == frame_id).all()
        gt_eval_map: dict[int, EvalResult] = {}
        evals = (
            s.query(EvalResult)
            .filter(
                EvalResult.frame_id == frame_id,
                EvalResult.run_name == run_name,
                EvalResult.ground_truth_id.isnot(None),
            )
            .all()
        )
        for er in evals:
            gt_eval_map[er.ground_truth_id] = er

        for gt in gts:
            er = gt_eval_map.get(gt.id)
            boxes.append({
                "source": "gt",
                "object_id": gt.object_id,
                "object_type": gt.object_type,
                "center_x": gt.center_x,
                "center_y": gt.center_y,
                "center_z": gt.center_z,
                "length": gt.length,
                "width": gt.width,
                "height": gt.height,
                "heading": gt.heading,
                "range": gt.range,
                "speed_x": gt.speed_x,
                "speed_y": gt.speed_y,
                "num_lidar_points": gt.num_lidar_points,
                "detection_difficulty": gt.detection_difficulty,
                "tracking_difficulty": gt.tracking_difficulty,
                "match_type": er.match_type if er else None,
                "matched_object_id": f"pred_{er.prediction_id}" if er and er.match_type == "TP" and er.prediction_id else None,
                "iou": er.iou if er else None,
                "sde": er.sde if er else None,
                "signed_sde": er.signed_sde if er else None,
                "heading_accuracy": er.heading_accuracy if er else None,
                "confidence": None,
            })

        # Build lookup from GT database ID → GT object_id for pairing
        gt_db_id_to_object_id = {gt.id: gt.object_id for gt in gts}

        # Predictions
        preds = s.query(Prediction).filter(Prediction.frame_id == frame_id).all()
        pred_eval_map: dict[int, EvalResult] = {}
        pred_evals = (
            s.query(EvalResult)
            .filter(
                EvalResult.frame_id == frame_id,
                EvalResult.run_name == run_name,
                EvalResult.prediction_id.isnot(None),
            )
            .all()
        )
        for er in pred_evals:
            pred_eval_map[er.prediction_id] = er

        for pred in preds:
            er = pred_eval_map.get(pred.id)
            matched_gt_oid = None
            if er and er.match_type == "TP" and er.ground_truth_id:
                matched_gt_oid = gt_db_id_to_object_id.get(er.ground_truth_id)
            boxes.append({
                "source": "pred",
                "object_id": f"pred_{pred.id}",
                "object_type": pred.object_type,
                "center_x": pred.center_x,
                "center_y": pred.center_y,
                "center_z": pred.center_z,
                "length": pred.length,
                "width": pred.width,
                "height": pred.height,
                "heading": pred.heading,
                "range": pred.range,
                "match_type": er.match_type if er else None,
                "matched_object_id": matched_gt_oid,
                "iou": er.iou if er else None,
                "sde": er.sde if er else None,
                "signed_sde": er.signed_sde if er else None,
                "heading_accuracy": er.heading_accuracy if er else None,
                "confidence": pred.confidence,
            })

    return boxes


# ── GET /api/failures ────────────────────────────────────────────────

@app.get("/api/failures")
def get_failures(
    run_name: str = "waymo_v1",
    failure_type: str = Query("worst_misses", alias="type"),
    limit: int = 20,
):
    """Return failure cases from the eval results."""
    db = _db()

    queries = {
        "worst_misses": text("""
            SELECT
                er.frame_id,
                gt.object_id AS highlight_object_id,
                CASE er.object_type
                    WHEN 1 THEN 'VEHICLE'
                    WHEN 2 THEN 'PEDESTRIAN'
                    WHEN 4 THEN 'CYCLIST'
                END AS class,
                ROUND(er.gt_range, 1) AS distance_m,
                gt.num_lidar_points   AS lidar_pts,
                gt.detection_difficulty AS difficulty
            FROM eval_results er
            JOIN ground_truths gt ON er.ground_truth_id = gt.id
            WHERE er.run_name  = :run AND er.match_type = 'FN'
            ORDER BY er.gt_range ASC, gt.num_lidar_points DESC
            LIMIT :lim
        """),
        "dangerous_errors": text("""
            SELECT
                er.frame_id,
                ('pred_' || er.prediction_id) AS highlight_object_id,
                CASE er.object_type
                    WHEN 1 THEN 'VEHICLE'
                    WHEN 2 THEN 'PEDESTRIAN'
                    WHEN 4 THEN 'CYCLIST'
                END AS class,
                ROUND(er.gt_range, 1)   AS distance_m,
                ROUND(er.iou, 4)        AS iou,
                ROUND(er.sde, 4)        AS sde,
                ROUND(er.signed_sde, 4) AS signed_sde,
                ROUND(er.confidence, 4) AS confidence
            FROM eval_results er
            WHERE er.run_name = :run
              AND er.match_type = 'TP'
              AND er.signed_sde > 0
            ORDER BY er.signed_sde DESC
            LIMIT :lim
        """),
        "hallucinations": text("""
            SELECT
                er.frame_id,
                ('pred_' || er.prediction_id) AS highlight_object_id,
                CASE er.object_type
                    WHEN 1 THEN 'VEHICLE'
                    WHEN 2 THEN 'PEDESTRIAN'
                    WHEN 4 THEN 'CYCLIST'
                END AS class,
                ROUND(er.confidence, 4) AS confidence
            FROM eval_results er
            WHERE er.run_name = :run AND er.match_type = 'FP'
            ORDER BY er.confidence DESC
            LIMIT :lim
        """),
    }

    sql = queries.get(failure_type)
    if sql is None:
        raise HTTPException(400, f"Unknown type: {failure_type}")

    with db.engine.connect() as conn:
        result = conn.execute(sql, {"run": run_name, "lim": limit})
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]

    return rows


# ── GET /api/frame_stats ──────────────────────────────────────────────

@app.get("/api/frame_stats")
def get_frame_stats(run_name: str = "waymo_v1"):
    """Return per-frame TP/FP/FN counts for the timeline scrubber."""
    db = _db()
    with db.engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT
                frame_id,
                SUM(CASE WHEN match_type='TP' THEN 1 ELSE 0 END) AS tp,
                SUM(CASE WHEN match_type='FP' THEN 1 ELSE 0 END) AS fp,
                SUM(CASE WHEN match_type='FN' THEN 1 ELSE 0 END) AS fn
            FROM eval_results
            WHERE run_name = :r
            GROUP BY frame_id
        """), {"r": run_name}).fetchall()
    return {str(r[0]): {"tp": r[1], "fp": r[2], "fn": r[3]} for r in rows}


# ── GET /api/runs ────────────────────────────────────────────────────

@app.get("/api/runs")
def list_runs():
    """Return all distinct eval run names."""
    db = _db()
    with db.engine.connect() as conn:
        result = conn.execute(text("SELECT DISTINCT run_name FROM eval_results ORDER BY run_name"))
        return [row[0] for row in result.fetchall()]


# ── GET /api/metrics ─────────────────────────────────────────────────

@app.get("/api/metrics")
def get_metrics(run_name: str = "waymo_v1"):
    """Aggregate metrics for the sidebar charts."""
    db = _db()
    out = {}

    with db.engine.connect() as conn:
        # By class
        rows = conn.execute(text("""
            SELECT
                CASE object_type WHEN 1 THEN 'VEH' WHEN 2 THEN 'PED' WHEN 4 THEN 'CYC' ELSE '?' END AS cls,
                SUM(CASE WHEN match_type='TP' THEN 1 ELSE 0 END) AS tp,
                SUM(CASE WHEN match_type='FP' THEN 1 ELSE 0 END) AS fp,
                SUM(CASE WHEN match_type='FN' THEN 1 ELSE 0 END) AS fn
            FROM eval_results WHERE run_name=:r GROUP BY object_type ORDER BY object_type
        """), {"r": run_name}).fetchall()
        out["by_class"] = [{"cls": r[0], "tp": r[1], "fp": r[2], "fn": r[3]} for r in rows]

        # By distance
        rows = conn.execute(text("""
            SELECT
                CASE WHEN gt_range<30 THEN '0-30' WHEN gt_range<50 THEN '30-50' ELSE '50+' END AS d,
                SUM(CASE WHEN match_type='TP' THEN 1 ELSE 0 END) AS tp,
                SUM(CASE WHEN match_type='FN' THEN 1 ELSE 0 END) AS fn,
                ROUND(AVG(CASE WHEN match_type='TP' THEN sde END),3) AS sde
            FROM eval_results WHERE run_name=:r AND gt_range IS NOT NULL
            GROUP BY d ORDER BY d
        """), {"r": run_name}).fetchall()
        out["by_distance"] = [{"d": r[0], "tp": r[1], "fn": r[2], "sde": r[3]} for r in rows]

    return out


# ── GET /api/pr_curve ────────────────────────────────────────────────

@app.get("/api/pr_curve")
def get_pr_curve(run_name: str = "waymo_v1"):
    """Compute precision-recall curve points per class."""
    db = _db()
    curves = {}

    with db.engine.connect() as conn:
        for obj_type, name in [(1, "VEHICLE"), (2, "PEDESTRIAN"), (4, "CYCLIST")]:
            rows = conn.execute(text("""
                SELECT confidence, match_type FROM eval_results
                WHERE run_name=:r AND object_type=:t AND match_type IN ('TP','FP')
                ORDER BY confidence DESC
            """), {"r": run_name, "t": obj_type}).fetchall()

            num_gt_result = conn.execute(text("""
                SELECT COUNT(*) FROM eval_results
                WHERE run_name=:r AND object_type=:t AND match_type IN ('TP','FN')
            """), {"r": run_name, "t": obj_type}).fetchone()
            num_gt = num_gt_result[0] if num_gt_result else 0

            if num_gt == 0:
                curves[name] = []
                continue

            tp_cum = 0
            fp_cum = 0
            points = []
            for conf, mt in rows:
                if mt == "TP":
                    tp_cum += 1
                else:
                    fp_cum += 1
                prec = tp_cum / (tp_cum + fp_cum)
                rec = tp_cum / num_gt
                points.append({"r": round(rec, 4), "p": round(prec, 4)})

            curves[name] = points

    return curves


# ── Triage helpers ───────────────────────────────────────────────────

def _load_triage_jsonl() -> list[dict]:
    """Parse triage_results.jsonl (supports both compact and pretty-printed)."""
    if not _TRIAGE_JSONL.exists():
        return []
    raw = _TRIAGE_JSONL.read_text(encoding="utf-8").lstrip()
    decoder = json.JSONDecoder()
    records, pos = [], 0
    while pos < len(raw):
        try:
            obj, end = decoder.raw_decode(raw, pos)
            records.append(obj)
            pos = end
            while pos < len(raw) and raw[pos] in " \t\n\r":
                pos += 1
        except json.JSONDecodeError:
            break
    return records


def _enrich_findings(frame_id: int, findings: list[dict], run_name: str = "waymo_v1") -> list[dict]:
    """
    Add `highlight_object_id` to each finding so the frontend can
    highlight the correct box in the 3D scene.

    The serialiser orders events the same way these queries do:
      FN  → ground_truths ordered by range ASC
      FP  → predictions ordered by confidence DESC
      TP  → ground_truths (matched) ordered by gt_range ASC
    """
    db = _db()
    with db.engine.connect() as conn:
        fn_ids = [
            r[0] for r in conn.execute(text("""
                SELECT gt.object_id
                FROM eval_results er
                JOIN ground_truths gt ON er.ground_truth_id = gt.id
                WHERE er.frame_id = :fid AND er.run_name = :run AND er.match_type = 'FN'
                ORDER BY gt.range ASC
            """), {"fid": frame_id, "run": run_name}).fetchall()
        ]
        fp_ids = [
            f"pred_{r[0]}" for r in conn.execute(text("""
                SELECT pr.id
                FROM eval_results er
                JOIN predictions pr ON er.prediction_id = pr.id
                WHERE er.frame_id = :fid AND er.run_name = :run AND er.match_type = 'FP'
                ORDER BY er.confidence DESC
            """), {"fid": frame_id, "run": run_name}).fetchall()
        ]
        tp_ids = [
            r[0] for r in conn.execute(text("""
                SELECT gt.object_id
                FROM eval_results er
                JOIN ground_truths gt ON er.ground_truth_id = gt.id
                WHERE er.frame_id = :fid AND er.run_name = :run AND er.match_type = 'TP'
                ORDER BY er.gt_range ASC
            """), {"fid": frame_id, "run": run_name}).fetchall()
        ]

    id_map = {"FN": fn_ids, "FP": fp_ids, "TP": tp_ids}
    enriched = []
    for f in findings:
        bucket = id_map.get(f.get("event_type", ""), [])
        idx = f.get("object_index", 1) - 1  # 1-based → 0-based
        enriched.append({
            **f,
            "highlight_object_id": bucket[idx] if 0 <= idx < len(bucket) else None,
        })
    return enriched


# ── GET /api/triage/summary ──────────────────────────────────────────

@app.get("/api/triage/summary")
def get_triage_summary():
    """
    Return per-frame severity counts for timeline colouring.

    Response: { frame_id: { critical, high, medium, low, tier2 }, ... }
    """
    records = _load_triage_jsonl()
    if not records:
        return {}
    summary = {}
    for r in records:
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "tier2": 0}
        for f in r.get("findings", []):
            sev = f.get("safety_severity") or ""
            if sev in counts:
                counts[sev] += 1
            if sev in ("low-medium",):
                counts["low"] += 1
            if f.get("tier") == 2:
                counts["tier2"] += 1
        summary[str(r["frame_id"])] = {
            **counts,
            "frame_summary": r.get("frame_summary", ""),
        }
    return summary


# ── GET /api/triage/{frame_id} ───────────────────────────────────────

@app.get("/api/triage/{frame_id}")
def get_triage_frame(frame_id: int, run_name: str = "waymo_v1"):
    """
    Return LLM triage findings for a single frame, enriched with
    highlight_object_id so the frontend can highlight boxes in 3D.
    """
    records = _load_triage_jsonl()
    result = next((r for r in records if r.get("frame_id") == frame_id), None)
    if result is None:
        return {"frame_id": frame_id, "findings": [], "frame_summary": "", "error": "no_triage_data"}

    enriched = _enrich_findings(frame_id, result.get("findings", []), run_name)
    return {**result, "findings": enriched}


# ── GET /api/frames/{id}/camera ──────────────────────────────────────

@app.get("/api/frames/{frame_id}/camera")
def get_camera(frame_id: int):
    """Return the front camera JPEG for a frame."""
    db = _db()
    with db.session() as s:
        frame = s.query(Frame).filter(Frame.id == frame_id).first()
        if frame is None:
            raise HTTPException(404, "Frame not found")
        seg = s.query(Segment).filter(Segment.id == frame.segment_id).first()

    tfrecord = find_tfrecord_for_context(seg.context_name, data_dir=_RAW_WAYMO_DIR)
    if tfrecord is None:
        raise HTTPException(404, "TFRecord not found")

    proto_frame = load_frame_from_tfrecord(tfrecord, frame.frame_index)
    jpeg = extract_front_camera(proto_frame)
    if jpeg is None:
        raise HTTPException(404, "No front camera image")

    return Response(content=jpeg, media_type="image/jpeg")

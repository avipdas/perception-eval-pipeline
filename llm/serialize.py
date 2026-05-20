"""Serialize 3-D perception evaluation data to natural language text.

Converts numerical bounding-box coordinates, ego-vehicle context, and
evaluation outcomes into descriptive text strings that an LLM can reason
over directly — following the approach demonstrated by Waymo's EMMA model,
which represents 3-D locations and scene state as unified text tokens.

Coordinate conventions (Waymo vehicle frame):
  +x = forward  (ahead of ego)
  +y = left      (driver's left)
  +z = up
  heading = rotation about +z; 0 = facing +x (same direction as ego forward)

Output format per frame (JSONL):
  {
    "frame_id":    <int>,
    "segment":     <str>,
    "frame_index": <int>,
    "timestamp_micros": <int>,
    "conditions":  <str>,
    "scene_text":  <str>,   # the full natural-language description
  }

Usage:
    python -m scripts.serialize_to_text                 # all frames, run waymo_v1
    python -m scripts.serialize_to_text --run default   # different eval run
    python -m scripts.serialize_to_text --frame 12      # single frame
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from sqlalchemy import text

from storage.database import DatabaseManager

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OBJECT_TYPE_NAMES = {
    1: "VEHICLE",
    2: "PEDESTRIAN",
    3: "SIGN",
    4: "CYCLIST",
}

# IoU thresholds per Waymo rules (used in interpretation text)
IOU_THRESHOLDS = {1: 0.7, 2: 0.5, 4: 0.5}

# Signed-SDE threshold above which we flag a localization error as dangerous
DANGEROUS_SDE_M = 0.30


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _norm_angle_deg(deg: float) -> float:
    """Normalise degrees to (-180, 180]."""
    deg = deg % 360
    if deg > 180:
        deg -= 360
    return deg


def bearing_deg(cx: float, cy: float) -> float:
    """
    Horizontal bearing from ego to object centre, in degrees.

    0° = straight ahead, +90° = hard left, -90° = hard right,
    ±180° = directly behind.  Wraps to (-180, 180].
    """
    return _norm_angle_deg(math.degrees(math.atan2(cy, cx)))


def bearing_description(cx: float, cy: float) -> str:
    """
    Return a clock-position zone from the ego's perspective.

    Zones (centred on 0° = forward):
      Directly ahead  : |b| <= 20°
      Ahead-left      : 20° < b <= 70°
      Left            : 70° < b <= 110°
      Behind-left     : 110° < b <= 160°
      Behind          : |b| > 160°
      Behind-right    : -160° < b <= -110°
      Right           : -110° < b <= -70°
      Ahead-right     : -70° < b <= -20°
    """
    b = bearing_deg(cx, cy)
    ab = abs(b)
    if ab <= 20:
        return "directly ahead"
    if ab > 160:
        return "directly behind"
    if b > 0:
        if b <= 70:
            return "ahead-left"
        if b <= 110:
            return "to the left"
        return "behind-left"
    else:
        if b >= -70:
            return "ahead-right"
        if b >= -110:
            return "to the right"
        return "behind-right"


def range_zone(range_m: float) -> str:
    if range_m < 10:
        return "immediate vicinity (<10 m)"
    if range_m < 30:
        return "near-field (10–30 m)"
    if range_m < 50:
        return "mid-range (30–50 m)"
    return "far-field (>50 m)"


def heading_description(heading_rad: float) -> str:
    """
    Describe the object's heading relative to the ego forward direction (+x).

    heading_rad is the box yaw in the vehicle frame (Waymo convention).
    0 rad = object facing same direction as ego (+x / forward).
    π rad = head-on toward ego.
    """
    deg = _norm_angle_deg(math.degrees(heading_rad))
    abs_deg = abs(deg)

    if abs_deg <= 15:
        return f"same direction as ego (≈0°)"
    if abs_deg >= 165:
        return f"head-on toward ego (≈180°)"
    direction = "left-relative" if deg > 0 else "right-relative"
    return f"{abs_deg:.0f}° {direction} of ego forward"


def velocity_description(speed_x: float, speed_y: float) -> str:
    """
    Return magnitude + compass-style direction in vehicle frame.

    speed_x = forward component, speed_y = leftward component.
    """
    mag = math.sqrt(speed_x ** 2 + speed_y ** 2)
    if mag < 0.3:
        return "stationary (< 0.3 m/s)"

    # compass label relative to vehicle frame axes
    deg = _norm_angle_deg(math.degrees(math.atan2(speed_y, speed_x)))
    if abs(deg) <= 22.5:
        compass = "forward"
    elif deg > 0:
        if deg <= 67.5:
            compass = "forward-left"
        elif deg <= 112.5:
            compass = "leftward"
        elif deg <= 157.5:
            compass = "rearward-left"
        else:
            compass = "rearward"
    else:
        if deg >= -67.5:
            compass = "forward-right"
        elif deg >= -112.5:
            compass = "rightward"
        elif deg >= -157.5:
            compass = "rearward-right"
        else:
            compass = "rearward"

    return f"{mag:.1f} m/s moving {compass}"


def size_description(length: float, width: float, height: float, otype: int) -> str:
    """
    Return a human-readable size summary including a size-class label.
    """
    exact = f"L {length:.1f} m × W {width:.1f} m × H {height:.1f} m"
    if otype == 1:  # VEHICLE
        if length < 3.5:
            size_class = "small vehicle (e.g. compact car)"
        elif length < 5.0:
            size_class = "mid-size vehicle (e.g. sedan/SUV)"
        else:
            size_class = "large vehicle (e.g. truck/van)"
        return f"{size_class}, dimensions {exact}"
    if otype == 2:  # PEDESTRIAN
        return f"pedestrian-sized, dimensions {exact}"
    if otype == 4:  # CYCLIST
        return f"cyclist-sized, dimensions {exact}"
    return f"dimensions {exact}"


def lidar_description(num_pts: int) -> str:
    if num_pts == 0:
        return "no LiDAR returns (ghost annotation)"
    if num_pts < 5:
        return f"very sparse ({num_pts} LiDAR pts — barely visible)"
    if num_pts < 20:
        return f"sparse ({num_pts} LiDAR pts — partially occluded)"
    if num_pts < 100:
        return f"moderate ({num_pts} LiDAR pts)"
    return f"dense ({num_pts} LiDAR pts — clearly visible)"


def difficulty_description(diff: int) -> str:
    if diff == 1:
        return "LEVEL_1 difficulty (well-visible)"
    if diff == 2:
        return "LEVEL_2 difficulty (occluded or distant)"
    return "difficulty unknown"


def sde_interpretation(signed_sde: float, otype: int) -> str:
    """
    Explain what the signed SDE value means for safety.

    Positive signed_sde = predicted nearest surface is FARTHER than reality
    → model underestimates how close the object is (dangerous).

    Negative signed_sde = predicted nearest surface is CLOSER than reality
    → model overestimates proximity (causes unnecessary caution).
    """
    abs_sde = abs(signed_sde)
    class_name = OBJECT_TYPE_NAMES.get(otype, "OBJECT")
    if abs_sde < 0.10:
        return "surface distance error negligible (< 10 cm)"
    if signed_sde > 0:
        severity = "CRITICAL" if abs_sde > DANGEROUS_SDE_M else "notable"
        return (
            f"{severity}: predicted surface is {abs_sde:.2f} m FARTHER from ego "
            f"than the real {class_name} — model underestimates proximity"
        )
    else:
        severity = "significant" if abs_sde > DANGEROUS_SDE_M else "minor"
        return (
            f"{severity}: predicted surface is {abs_sde:.2f} m CLOSER to ego "
            f"than the real {class_name} — model overestimates proximity"
        )


def iou_description(iou: float, otype: int) -> str:
    thresh = IOU_THRESHOLDS.get(otype, 0.5)
    if iou >= thresh + 0.15:
        qual = "high-quality match"
    elif iou >= thresh:
        qual = "acceptable match (above threshold)"
    else:
        qual = "poor overlap (below match threshold)"
    return f"IoU {iou:.3f} ({qual})"


# ---------------------------------------------------------------------------
# Scene-context serializer (ego vehicle + segment metadata)
# ---------------------------------------------------------------------------

def _conditions_text(location: str | None, weather: str | None, tod: str | None) -> str:
    parts = []
    if tod:
        parts.append(tod.replace("_", " ").lower())
    if weather:
        parts.append(weather.replace("_", " ").lower())
    if location:
        parts.append(f"location: {location}")
    return ", ".join(parts) if parts else "conditions unknown"


def _ego_text() -> str:
    """
    Ego-vehicle state.  All boxes are in the vehicle frame, so the ego is
    always at the origin facing +x.  Absolute pose/speed are not stored in
    this pipeline's database; relative geometry is fully captured by the box
    coordinates and the scene-level metadata.
    """
    return (
        "Ego vehicle: origin (0.0, 0.0, 0.0 m), heading along +x (forward). "
        "All object positions are expressed in this vehicle-centric frame. "
        "Ego speed and global map position are not stored in the eval database."
    )


# ---------------------------------------------------------------------------
# Per-box serializers
# ---------------------------------------------------------------------------

def serialize_missed_gt(
    gt_id: int,
    object_type: int,
    cx: float,
    cy: float,
    cz: float,
    length: float,
    width: float,
    height: float,
    heading: float,
    range_m: float,
    num_lidar_pts: int,
    detection_difficulty: int,
    speed_x: float,
    speed_y: float,
    idx: int,
) -> str:
    """Convert one missed ground-truth box (FN) to a natural-language sentence."""
    class_name = OBJECT_TYPE_NAMES.get(object_type, f"TYPE_{object_type}")
    b_deg = bearing_deg(cx, cy)
    zone = bearing_description(cx, cy)
    rang_zone = range_zone(range_m)

    lines = [
        f"  [{idx}] MISSED {class_name} at {range_m:.1f} m ({rang_zone}), "
        f"{zone} (bearing {b_deg:+.0f}°).",
        f"      Box: {size_description(length, width, height, object_type)}.",
        f"      Heading: {heading_description(heading)}.",
        f"      Velocity: {velocity_description(speed_x, speed_y)}.",
        f"      Visibility: {lidar_description(num_lidar_pts)}, "
        f"{difficulty_description(detection_difficulty)}.",
        f"      3-D center: ({cx:.2f}, {cy:.2f}, {cz:.2f}) m.",
    ]

    # Safety annotation
    if range_m < 20 and num_lidar_pts >= 10:
        lines.append(
            f"      ⚠ Safety note: close-range {class_name.lower()} "
            f"with adequate LiDAR returns was entirely missed."
        )
    elif detection_difficulty == 2 and range_m < 40:
        lines.append(
            f"      Note: Level-2 difficulty {class_name.lower()} at medium range."
        )

    return "\n".join(lines)


def serialize_false_positive(
    pred_id: int,
    object_type: int,
    cx: float,
    cy: float,
    cz: float,
    length: float,
    width: float,
    height: float,
    heading: float,
    range_m: float,
    confidence: float,
    idx: int,
) -> str:
    """Convert one phantom prediction (FP) to a natural-language sentence."""
    class_name = OBJECT_TYPE_NAMES.get(object_type, f"TYPE_{object_type}")
    b_deg = bearing_deg(cx, cy)
    zone = bearing_description(cx, cy)
    rang_zone = range_zone(range_m)

    conf_qual = (
        "HIGH confidence" if confidence >= 0.8 else
        "medium confidence" if confidence >= 0.5 else
        "low confidence"
    )

    lines = [
        f"  [{idx}] PHANTOM {class_name} predicted at {range_m:.1f} m ({rang_zone}), "
        f"{zone} (bearing {b_deg:+.0f}°).",
        f"      Box: {size_description(length, width, height, object_type)}.",
        f"      Heading: {heading_description(heading)}.",
        f"      Confidence: {confidence:.3f} ({conf_qual}).",
        f"      3-D center: ({cx:.2f}, {cy:.2f}, {cz:.2f}) m.",
    ]

    if confidence >= 0.8:
        lines.append(
            f"      ⚠ Safety note: high-confidence hallucination may trigger "
            f"unnecessary braking or avoidance manoeuvre."
        )

    return "\n".join(lines)


def serialize_true_positive(
    object_type: int,
    confidence: float,
    iou: float,
    signed_sde: float,
    heading_accuracy: float,
    gt_range: float,
    gt_cx: float,
    gt_cy: float,
    gt_cz: float,
    gt_length: float,
    gt_width: float,
    gt_height: float,
    gt_heading: float,
    gt_speed_x: float,
    gt_speed_y: float,
    idx: int,
) -> str:
    """Convert one matched detection (TP) with its localization quality."""
    class_name = OBJECT_TYPE_NAMES.get(object_type, f"TYPE_{object_type}")
    b_deg = bearing_deg(gt_cx, gt_cy)
    zone = bearing_description(gt_cx, gt_cy)
    rang_zone = range_zone(gt_range)
    heading_acc_deg = math.degrees(heading_accuracy) if heading_accuracy is not None else None

    lines = [
        f"  [{idx}] DETECTED {class_name} at {gt_range:.1f} m ({rang_zone}), "
        f"{zone} (bearing {b_deg:+.0f}°).",
        f"      GT box: {size_description(gt_length, gt_width, gt_height, object_type)}.",
        f"      GT heading: {heading_description(gt_heading)}.",
        f"      GT velocity: {velocity_description(gt_speed_x, gt_speed_y)}.",
        f"      GT center: ({gt_cx:.2f}, {gt_cy:.2f}, {gt_cz:.2f}) m.",
        f"      Match quality: {iou_description(iou, object_type)}, "
        f"confidence {confidence:.3f}.",
    ]

    if signed_sde is not None:
        lines.append(f"      Localization: {sde_interpretation(signed_sde, object_type)}.")

    if heading_acc_deg is not None:
        if heading_acc_deg < 5:
            lines.append(f"      Heading accuracy: excellent ({heading_acc_deg:.1f}°).")
        elif heading_acc_deg < 20:
            lines.append(f"      Heading accuracy: acceptable ({heading_acc_deg:.1f}° error).")
        else:
            lines.append(
                f"      Heading accuracy: poor ({heading_acc_deg:.1f}° error) — "
                f"may affect motion-prediction quality."
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-frame scene assembler
# ---------------------------------------------------------------------------

_FN_QUERY = text("""
    SELECT
        er.id           AS er_id,
        er.object_type,
        gt.id           AS gt_id,
        gt.center_x,  gt.center_y,  gt.center_z,
        gt.length,    gt.width,     gt.height,    gt.heading,
        gt.range,
        gt.num_lidar_points,
        gt.detection_difficulty,
        COALESCE(gt.speed_x, 0.0) AS speed_x,
        COALESCE(gt.speed_y, 0.0) AS speed_y
    FROM eval_results er
    JOIN ground_truths gt ON er.ground_truth_id = gt.id
    WHERE er.run_name   = :run
      AND er.frame_id   = :fid
      AND er.match_type = 'FN'
    ORDER BY gt.range ASC
""")

_FP_QUERY = text("""
    SELECT
        er.id           AS er_id,
        er.object_type,
        pr.id           AS pred_id,
        pr.center_x,  pr.center_y,  pr.center_z,
        pr.length,    pr.width,     pr.height,    pr.heading,
        pr.range,
        er.confidence
    FROM eval_results er
    JOIN predictions pr ON er.prediction_id = pr.id
    WHERE er.run_name   = :run
      AND er.frame_id   = :fid
      AND er.match_type = 'FP'
    ORDER BY er.confidence DESC
""")

_TP_QUERY = text("""
    SELECT
        er.object_type,
        er.confidence,
        er.iou,
        er.signed_sde,
        er.heading_accuracy,
        er.gt_range,
        gt.center_x   AS gt_cx,  gt.center_y AS gt_cy,  gt.center_z AS gt_cz,
        gt.length     AS gt_length, gt.width  AS gt_width, gt.height  AS gt_height,
        gt.heading    AS gt_heading,
        COALESCE(gt.speed_x, 0.0) AS gt_speed_x,
        COALESCE(gt.speed_y, 0.0) AS gt_speed_y
    FROM eval_results er
    JOIN ground_truths gt ON er.ground_truth_id  = gt.id
    WHERE er.run_name   = :run
      AND er.frame_id   = :fid
      AND er.match_type = 'TP'
    ORDER BY er.gt_range ASC
""")

_FRAME_META_QUERY = text("""
    SELECT
        f.id            AS frame_id,
        f.frame_index,
        f.timestamp_micros,
        s.context_name,
        s.location,
        s.weather,
        s.time_of_day
    FROM frames f
    JOIN segments s ON f.segment_id = s.id
    WHERE f.id = :fid
""")


@dataclass
class FrameRecord:
    """All serialized data for one frame."""
    frame_id: int
    segment: str
    frame_index: int
    timestamp_micros: int
    conditions: str
    scene_text: str
    fn_count: int = 0
    fp_count: int = 0
    tp_count: int = 0
    metadata: dict = field(default_factory=dict)


def serialize_frame(frame_id: int, run_name: str, db: DatabaseManager) -> FrameRecord:
    """
    Query all eval results for one frame and return a FrameRecord
    whose `scene_text` contains the full natural-language description.
    """
    params = {"run": run_name, "fid": frame_id}

    with db.engine.connect() as conn:
        meta_row = conn.execute(_FRAME_META_QUERY, {"fid": frame_id}).mappings().first()
        if meta_row is None:
            raise ValueError(f"Frame {frame_id} not found in database.")

        fns  = conn.execute(_FN_QUERY,  params).mappings().all()
        fps  = conn.execute(_FP_QUERY,  params).mappings().all()
        tps  = conn.execute(_TP_QUERY,  params).mappings().all()

    location    = meta_row["location"]
    weather     = meta_row["weather"]
    tod         = meta_row["time_of_day"]
    context_name = meta_row["context_name"]
    frame_index  = meta_row["frame_index"]
    timestamp    = meta_row["timestamp_micros"]

    conditions = _conditions_text(location, weather, tod)

    # -----------------------------------------------------------------------
    # Build the scene text
    # -----------------------------------------------------------------------
    header = (
        f"SCENE: frame {frame_index} (frame_id={frame_id})\n"
        f"SEGMENT: {context_name[:12]}… (Waymo Open Dataset)\n"
        f"TIMESTAMP: {timestamp / 1e6:.3f} s\n"
        f"CONDITIONS: {conditions}\n"
        f"{_ego_text()}\n"
    )

    # --- Missed detections (FN) ---
    if fns:
        fn_lines = [
            f"\nMISSED DETECTIONS ({len(fns)} object{'s' if len(fns) != 1 else ''} "
            f"the model failed to detect):"
        ]
        for i, row in enumerate(fns, 1):
            fn_lines.append(serialize_missed_gt(
                gt_id=row["gt_id"],
                object_type=row["object_type"],
                cx=row["center_x"],
                cy=row["center_y"],
                cz=row["center_z"],
                length=row["length"],
                width=row["width"],
                height=row["height"],
                heading=row["heading"],
                range_m=row["range"],
                num_lidar_pts=row["num_lidar_points"],
                detection_difficulty=row["detection_difficulty"],
                speed_x=row["speed_x"],
                speed_y=row["speed_y"],
                idx=i,
            ))
        fn_section = "\n".join(fn_lines)
    else:
        fn_section = "\nMISSED DETECTIONS: none in this frame."

    # --- False positives (FP) ---
    if fps:
        fp_lines = [
            f"\nPHANTOM PREDICTIONS ({len(fps)} false positive{'s' if len(fps) != 1 else ''} "
            f"with no matching ground truth):"
        ]
        for i, row in enumerate(fps, 1):
            fp_lines.append(serialize_false_positive(
                pred_id=row["pred_id"],
                object_type=row["object_type"],
                cx=row["center_x"],
                cy=row["center_y"],
                cz=row["center_z"],
                length=row["length"],
                width=row["width"],
                height=row["height"],
                heading=row["heading"],
                range_m=row["range"],
                confidence=row["confidence"],
                idx=i,
            ))
        fp_section = "\n".join(fp_lines)
    else:
        fp_section = "\nPHANTOM PREDICTIONS: none in this frame."

    # --- True positives (TP with localization detail) ---
    if tps:
        tp_lines = [
            f"\nDETECTED OBJECTS ({len(tps)} true positive{'s' if len(tps) != 1 else ''}):"
        ]
        for i, row in enumerate(tps, 1):
            tp_lines.append(serialize_true_positive(
                object_type=row["object_type"],
                confidence=row["confidence"],
                iou=row["iou"],
                signed_sde=row["signed_sde"],
                heading_accuracy=row["heading_accuracy"],
                gt_range=row["gt_range"],
                gt_cx=row["gt_cx"],
                gt_cy=row["gt_cy"],
                gt_cz=row["gt_cz"],
                gt_length=row["gt_length"],
                gt_width=row["gt_width"],
                gt_height=row["gt_height"],
                gt_heading=row["gt_heading"],
                gt_speed_x=row["gt_speed_x"],
                gt_speed_y=row["gt_speed_y"],
                idx=i,
            ))
        tp_section = "\n".join(tp_lines)
    else:
        tp_section = "\nDETECTED OBJECTS: none matched in this frame."

    scene_text = header + fn_section + fp_section + tp_section

    return FrameRecord(
        frame_id=frame_id,
        segment=context_name,
        frame_index=frame_index,
        timestamp_micros=timestamp,
        conditions=conditions,
        scene_text=scene_text,
        fn_count=len(fns),
        fp_count=len(fps),
        tp_count=len(tps),
        metadata={
            "location": location,
            "weather": weather,
            "time_of_day": tod,
        },
    )


# ---------------------------------------------------------------------------
# Batch serializer
# ---------------------------------------------------------------------------

_ALL_FRAME_IDS_QUERY = text("""
    SELECT DISTINCT frame_id
    FROM eval_results
    WHERE run_name = :run
    ORDER BY frame_id
""")


def iter_frames(
    run_name: str,
    db: DatabaseManager,
    frame_id: int | None = None,
) -> Iterator[FrameRecord]:
    """
    Yield FrameRecord objects for every frame in the eval run.

    If `frame_id` is given, only that frame is serialized.
    """
    if frame_id is not None:
        yield serialize_frame(frame_id, run_name, db)
        return

    with db.engine.connect() as conn:
        ids = [r[0] for r in conn.execute(_ALL_FRAME_IDS_QUERY, {"run": run_name})]

    total = len(ids)
    for i, fid in enumerate(ids, 1):
        record = serialize_frame(fid, run_name, db)
        print(
            f"  [{i:>3}/{total}] frame_id={fid:>4} "
            f"FN={record.fn_count} FP={record.fp_count} TP={record.tp_count}"
        )
        yield record


def save_jsonl(
    output_path: Path,
    run_name: str,
    db: DatabaseManager,
    frame_id: int | None = None,
    pretty: bool = False,
) -> int:
    """
    Write serialized frames to a JSONL file.

    Returns number of frames written.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as fh:
        for record in iter_frames(run_name, db, frame_id=frame_id):
            entry = {
                "frame_id":         record.frame_id,
                "segment":          record.segment,
                "frame_index":      record.frame_index,
                "timestamp_micros": record.timestamp_micros,
                "conditions":       record.conditions,
                "fn_count":         record.fn_count,
                "fp_count":         record.fp_count,
                "tp_count":         record.tp_count,
                "metadata":         record.metadata,
                "scene_text":       record.scene_text,
            }
            if pretty:
                fh.write(json.dumps(entry, indent=2, ensure_ascii=False) + "\n")
            else:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            count += 1
    return count

"""Triage taxonomy for perception evaluation failures.

Two-tier structure, inspired by how AV safety teams escalate defects:

  Tier 1 — Operational Triage
      High-volume issues that can be auto-screened or batch-reviewed.
      Usually flagged before an engineering investigation is opened.
      Root cause is often in the dataset, annotation process, or
      known sensor-range limits rather than model architecture.

  Tier 2 — Technical Triage
      Deep-dive defects that require an engineer to understand why the
      perception stack failed.  Each code maps to a specific failure
      mechanism with a defined safety severity.

The canonical list is FAILURE_MODES — a plain list of dicts so it can be
serialised to JSON and embedded verbatim in an LLM system prompt.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Tier 1 — Operational Triage
# ---------------------------------------------------------------------------

TIER1: list[dict[str, Any]] = [
    {
        "code": "T1_GHOST_ANNOTATION",
        "tier": 1,
        "label": "Ghost / sparse annotation",
        "description": (
            "Ground-truth box has zero or very few LiDAR returns (< 5 pts), "
            "suggesting the annotated object may not actually be present in the "
            "point cloud.  Treat as a dataset quality issue first."
        ),
        "primary_signal": "FN with num_lidar_points < 5",
        "evidence_fields": ["num_lidar_points", "detection_difficulty"],
        "safety_severity": "low",
        "recommended_action": "Re-queue frame for annotation review; do not count in recall metrics.",
    },
    {
        "code": "T1_RANGE_ROLLOFF",
        "tier": 1,
        "label": "Expected range roll-off",
        "description": (
            "Miss or false positive occurs beyond 60 m where LiDAR point density "
            "naturally degrades.  This is expected sensor-physics behaviour, not a "
            "model defect, unless the object is a vehicle (higher safety bar)."
        ),
        "primary_signal": "FN or FP with range > 60 m",
        "evidence_fields": ["range", "num_lidar_points"],
        "safety_severity": "low",
        "recommended_action": "Log for range-performance tracking; not an immediate engineering ticket.",
    },
    {
        "code": "T1_LOW_CONFIDENCE_FP",
        "tier": 1,
        "label": "Below-threshold confidence hallucination",
        "description": (
            "False positive prediction with confidence below 0.35.  These are "
            "filtered by most downstream consumers; they inflate FP counts but "
            "rarely affect planning."
        ),
        "primary_signal": "FP with confidence < 0.35",
        "evidence_fields": ["confidence"],
        "safety_severity": "low",
        "recommended_action": "Adjust score-filtering threshold; batch-review for score calibration.",
    },
    {
        "code": "T1_KNOWN_OCCLUSION_LEVEL2",
        "tier": 1,
        "label": "Level-2 occlusion miss (expected difficulty)",
        "description": (
            "Missed detection on a Waymo Level-2 difficulty object (heavily occluded "
            "or with very few LiDAR points).  Model behaviour is within expected "
            "difficulty-stratified recall bounds."
        ),
        "primary_signal": "FN with detection_difficulty == 2 and num_lidar_points < 20",
        "evidence_fields": ["detection_difficulty", "num_lidar_points", "range"],
        "safety_severity": "low-medium",
        "recommended_action": "Track Level-2 recall trend; escalate only if regression from baseline.",
    },
    {
        "code": "T1_MINOR_LOCALIZATION_OFFSET",
        "tier": 1,
        "label": "Minor localization offset",
        "description": (
            "True positive with a small surface-distance error (|signed_sde| < 0.15 m). "
            "Within acceptable tolerance for most downstream uses; not a safety concern."
        ),
        "primary_signal": "TP with |signed_sde| < 0.15",
        "evidence_fields": ["signed_sde", "iou"],
        "safety_severity": "negligible",
        "recommended_action": "No engineering action needed; log for regression baseline.",
    },
]

# ---------------------------------------------------------------------------
# Tier 2 — Technical Triage
# ---------------------------------------------------------------------------

TIER2: list[dict[str, Any]] = [
    {
        "code": "T2_NEAR_FIELD_CRITICAL_MISS",
        "tier": 2,
        "label": "Near-field critical miss",
        "description": (
            "Object with adequate LiDAR visibility (≥ 10 pts) was entirely missed "
            "within 20 m of the ego vehicle.  The model had enough sensor data to "
            "detect the object and failed.  Highest safety priority."
        ),
        "primary_signal": "FN with range < 20 m and num_lidar_points >= 10",
        "evidence_fields": ["range", "num_lidar_points", "object_type", "heading"],
        "safety_severity": "critical",
        "recommended_action": (
            "Immediate engineering investigation.  Check if object is in a known "
            "blind spot, edge class, or if the frame represents a model regression."
        ),
    },
    {
        "code": "T2_PEDESTRIAN_CYCLIST_MISS",
        "tier": 2,
        "label": "Vulnerable road user miss",
        "description": (
            "Missed detection of a PEDESTRIAN or CYCLIST at any range with at least "
            "moderate LiDAR returns (≥ 5 pts).  Vulnerable road users have zero "
            "tolerance for false negatives regardless of distance."
        ),
        "primary_signal": "FN with object_type in [2, 4] and num_lidar_points >= 5",
        "evidence_fields": ["object_type", "range", "num_lidar_points", "speed_x", "speed_y"],
        "safety_severity": "critical",
        "recommended_action": (
            "File safety-critical ticket.  Cross-check with camera modality if "
            "LiDAR-camera fusion is used."
        ),
    },
    {
        "code": "T2_DEPTH_UNDERESTIMATION",
        "tier": 2,
        "label": "Depth underestimation (predicted farther than reality)",
        "description": (
            "True positive whose predicted nearest surface is significantly farther "
            "from the ego than the ground-truth surface (signed_sde > 0.30 m).  "
            "The model believes it has more clearance than it actually does, which "
            "can lead to unsafe manoeuvres."
        ),
        "primary_signal": "TP with signed_sde > 0.30",
        "evidence_fields": ["signed_sde", "iou", "range", "object_type"],
        "safety_severity": "high",
        "recommended_action": (
            "Investigate depth estimation branch.  Check if correlated with "
            "object aspect angle (heading relative to ego)."
        ),
    },
    {
        "code": "T2_HEADING_CONFUSION",
        "tier": 2,
        "label": "Heading / orientation confusion",
        "description": (
            "Matched detection with large heading error (heading_accuracy > 45°). "
            "A wrong heading causes the motion predictor to forecast the object "
            "moving in the wrong direction, leading to incorrect collision-risk scores."
        ),
        "primary_signal": "TP with heading_accuracy > 0.785 rad (45°)",
        "evidence_fields": ["heading_accuracy", "iou", "object_type", "range"],
        "safety_severity": "high",
        "recommended_action": (
            "Check if error correlates with symmetrical objects (parked vehicles) "
            "or long-range detections where orientation is ambiguous."
        ),
    },
    {
        "code": "T2_HIGH_CONFIDENCE_HALLUCINATION",
        "tier": 2,
        "label": "High-confidence hallucination",
        "description": (
            "False positive with confidence ≥ 0.70.  The model was very certain it "
            "detected an object that does not exist.  Can trigger phantom braking or "
            "avoidance in the planner."
        ),
        "primary_signal": "FP with confidence >= 0.70",
        "evidence_fields": ["confidence", "range", "object_type", "center_x", "center_y"],
        "safety_severity": "high",
        "recommended_action": (
            "Examine point cloud around predicted centre for reflective surfaces, "
            "glass, or adversarial geometry.  Check score calibration."
        ),
    },
    {
        "code": "T2_CLOSE_RANGE_HALLUCINATION",
        "tier": 2,
        "label": "Close-range hallucination",
        "description": (
            "False positive within 25 m of ego at any confidence level.  Phantom "
            "objects in the immediate vicinity can cause the planner to brake hard "
            "or steer sharply."
        ),
        "primary_signal": "FP with range < 25 m",
        "evidence_fields": ["range", "confidence", "object_type"],
        "safety_severity": "high",
        "recommended_action": (
            "Review the specific spatial region for persistent artifacts "
            "(road markings, guardrails, reflections)."
        ),
    },
    {
        "code": "T2_MID_RANGE_STRUCTURED_MISS",
        "tier": 2,
        "label": "Mid-range structured-scene miss",
        "description": (
            "Object missed at 20–55 m with sufficient LiDAR density (≥ 20 pts). "
            "Not near-field critical, but occurs where the model should have confident "
            "detections.  Often indicates a generalisation gap (lighting, weather, "
            "object sub-type)."
        ),
        "primary_signal": "FN with 20 <= range <= 55 and num_lidar_points >= 20",
        "evidence_fields": ["range", "num_lidar_points", "object_type", "detection_difficulty"],
        "safety_severity": "medium",
        "recommended_action": (
            "Cluster by object type and scene conditions.  Check if confined to "
            "specific segment or consistent across segments."
        ),
    },
    {
        "code": "T2_LOCALIZATION_AMBIGUITY",
        "tier": 2,
        "label": "Localization ambiguity (large SDE despite good IoU)",
        "description": (
            "True positive with acceptable IoU (≥ threshold) but SDE > 0.40 m. "
            "The box overlaps the ground truth adequately but the nearest-surface "
            "estimate is significantly off.  Indicates a bias in the regression head "
            "or box refinement step."
        ),
        "primary_signal": "TP with sde > 0.40 and iou >= threshold",
        "evidence_fields": ["sde", "signed_sde", "iou", "object_type", "range"],
        "safety_severity": "medium",
        "recommended_action": (
            "Investigate box regression or NMS suppression.  Check if SDE "
            "correlates with object size (large vehicles more affected)."
        ),
    },
]

# ---------------------------------------------------------------------------
# Combined canonical list
# ---------------------------------------------------------------------------

FAILURE_MODES: list[dict[str, Any]] = TIER1 + TIER2

# Fast lookup by code
FAILURE_MODE_BY_CODE: dict[str, dict[str, Any]] = {
    fm["code"]: fm for fm in FAILURE_MODES
}

# Codes grouped by tier
TIER1_CODES = [fm["code"] for fm in TIER1]
TIER2_CODES = [fm["code"] for fm in TIER2]

# Compact reference string suitable for embedding in a prompt
TAXONOMY_SUMMARY = "\n".join(
    f'  {fm["code"]} (Tier {fm["tier"]}) — {fm["label"]}: {fm["description"]}'
    for fm in FAILURE_MODES
)

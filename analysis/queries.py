"""SQL analytical queries for slicing evaluation results.

Each function runs a single SQL query against the eval_results table
(populated by run_evaluation.py) and returns a pandas DataFrame.

The queries slice performance across the dimensions that matter most
for autonomous driving safety:
  - Distance from ego vehicle (near vs. far)
  - Object class (vehicle vs. pedestrian vs. cyclist)
  - Occlusion / difficulty level
  - LiDAR point density
  - Failure case analysis (worst misses, dangerous errors)
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from storage.database import DatabaseManager


# ---------------------------------------------------------------------------
# 1. High-level summary
# ---------------------------------------------------------------------------

def summary_statistics(db: DatabaseManager, run_name: str) -> pd.DataFrame:
    """Total TP / FP / FN counts and overall precision and recall."""

    sql = text("""
        SELECT
            SUM(CASE WHEN match_type = 'TP' THEN 1 ELSE 0 END) AS tp,
            SUM(CASE WHEN match_type = 'FP' THEN 1 ELSE 0 END) AS fp,
            SUM(CASE WHEN match_type = 'FN' THEN 1 ELSE 0 END) AS fn,
            ROUND(
                CAST(SUM(CASE WHEN match_type = 'TP' THEN 1 ELSE 0 END) AS FLOAT)
                / NULLIF(SUM(CASE WHEN match_type IN ('TP','FP') THEN 1 ELSE 0 END), 0),
            4) AS precision,
            ROUND(
                CAST(SUM(CASE WHEN match_type = 'TP' THEN 1 ELSE 0 END) AS FLOAT)
                / NULLIF(SUM(CASE WHEN match_type IN ('TP','FN') THEN 1 ELSE 0 END), 0),
            4) AS recall,
            ROUND(AVG(CASE WHEN match_type = 'TP' THEN iou  END), 4) AS mean_iou,
            ROUND(AVG(CASE WHEN match_type = 'TP' THEN sde  END), 4) AS mean_sde
        FROM eval_results
        WHERE run_name = :run
    """)

    with db.engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"run": run_name})


# ---------------------------------------------------------------------------
# 2. Performance by distance from ego vehicle
# ---------------------------------------------------------------------------

def performance_by_distance(db: DatabaseManager, run_name: str) -> pd.DataFrame:
    """Bucket gt_range into 0-30 m, 30-50 m, 50 m+ and compute metrics."""

    sql = text("""
        SELECT
            CASE
                WHEN gt_range IS NULL THEN 'unknown'
                WHEN gt_range <  30   THEN '0-30m'
                WHEN gt_range <  50   THEN '30-50m'
                ELSE                       '50m+'
            END AS distance,
            SUM(CASE WHEN match_type = 'TP' THEN 1 ELSE 0 END) AS tp,
            SUM(CASE WHEN match_type = 'FP' THEN 1 ELSE 0 END) AS fp,
            SUM(CASE WHEN match_type = 'FN' THEN 1 ELSE 0 END) AS fn,
            ROUND(
                CAST(SUM(CASE WHEN match_type = 'TP' THEN 1 ELSE 0 END) AS FLOAT)
                / NULLIF(SUM(CASE WHEN match_type IN ('TP','FP') THEN 1 ELSE 0 END), 0),
            4) AS precision,
            ROUND(
                CAST(SUM(CASE WHEN match_type = 'TP' THEN 1 ELSE 0 END) AS FLOAT)
                / NULLIF(SUM(CASE WHEN match_type IN ('TP','FN') THEN 1 ELSE 0 END), 0),
            4) AS recall,
            ROUND(AVG(CASE WHEN match_type = 'TP' THEN iou  END), 4) AS mean_iou,
            ROUND(AVG(CASE WHEN match_type = 'TP' THEN sde  END), 4) AS mean_sde
        FROM eval_results
        WHERE run_name = :run
        GROUP BY distance
        ORDER BY distance
    """)

    with db.engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"run": run_name})


# ---------------------------------------------------------------------------
# 3. Performance by object class
# ---------------------------------------------------------------------------

def performance_by_class(db: DatabaseManager, run_name: str) -> pd.DataFrame:
    """One row per object type with TP / FP / FN and metrics."""

    sql = text("""
        SELECT
            CASE object_type
                WHEN 1 THEN 'VEHICLE'
                WHEN 2 THEN 'PEDESTRIAN'
                WHEN 4 THEN 'CYCLIST'
                ELSE        'OTHER'
            END AS class,
            SUM(CASE WHEN match_type = 'TP' THEN 1 ELSE 0 END) AS tp,
            SUM(CASE WHEN match_type = 'FP' THEN 1 ELSE 0 END) AS fp,
            SUM(CASE WHEN match_type = 'FN' THEN 1 ELSE 0 END) AS fn,
            ROUND(
                CAST(SUM(CASE WHEN match_type = 'TP' THEN 1 ELSE 0 END) AS FLOAT)
                / NULLIF(SUM(CASE WHEN match_type IN ('TP','FP') THEN 1 ELSE 0 END), 0),
            4) AS precision,
            ROUND(
                CAST(SUM(CASE WHEN match_type = 'TP' THEN 1 ELSE 0 END) AS FLOAT)
                / NULLIF(SUM(CASE WHEN match_type IN ('TP','FN') THEN 1 ELSE 0 END), 0),
            4) AS recall,
            ROUND(AVG(CASE WHEN match_type = 'TP' THEN iou              END), 4) AS mean_iou,
            ROUND(AVG(CASE WHEN match_type = 'TP' THEN heading_accuracy END), 4) AS mean_heading,
            ROUND(AVG(CASE WHEN match_type = 'TP' THEN sde              END), 4) AS mean_sde
        FROM eval_results
        WHERE run_name = :run
        GROUP BY object_type
        ORDER BY object_type
    """)

    with db.engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"run": run_name})


# ---------------------------------------------------------------------------
# 4. Distance x Class cross-tabulation
# ---------------------------------------------------------------------------

def performance_by_distance_and_class(
    db: DatabaseManager, run_name: str,
) -> pd.DataFrame:
    """Combined slice: how does each class perform at each distance?"""

    sql = text("""
        SELECT
            CASE
                WHEN gt_range IS NULL THEN 'unknown'
                WHEN gt_range <  30   THEN '0-30m'
                WHEN gt_range <  50   THEN '30-50m'
                ELSE                       '50m+'
            END AS distance,
            CASE object_type
                WHEN 1 THEN 'VEHICLE'
                WHEN 2 THEN 'PEDESTRIAN'
                WHEN 4 THEN 'CYCLIST'
            END AS class,
            SUM(CASE WHEN match_type = 'TP' THEN 1 ELSE 0 END) AS tp,
            SUM(CASE WHEN match_type = 'FN' THEN 1 ELSE 0 END) AS fn,
            ROUND(
                CAST(SUM(CASE WHEN match_type = 'TP' THEN 1 ELSE 0 END) AS FLOAT)
                / NULLIF(SUM(CASE WHEN match_type IN ('TP','FN') THEN 1 ELSE 0 END), 0),
            4) AS recall,
            ROUND(AVG(CASE WHEN match_type = 'TP' THEN sde END), 4) AS mean_sde
        FROM eval_results
        WHERE run_name = :run
        GROUP BY distance, class
        ORDER BY distance, class
    """)

    with db.engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"run": run_name})


# ---------------------------------------------------------------------------
# 5. Performance by detection difficulty (Waymo's occlusion proxy)
# ---------------------------------------------------------------------------

def performance_by_difficulty(
    db: DatabaseManager, run_name: str,
) -> pd.DataFrame:
    """Slice by Waymo's detection_difficulty field.

    LEVEL_1 objects are well-visible (many LiDAR points, minimal
    occlusion).  LEVEL_2 objects are partially occluded or distant.
    Joins with ground_truths to access difficulty metadata.
    """

    sql = text("""
        SELECT
            CASE gt.detection_difficulty
                WHEN 1 THEN 'LEVEL_1 (easy)'
                WHEN 2 THEN 'LEVEL_2 (hard)'
                ELSE        'UNKNOWN'
            END AS difficulty,
            CASE er.object_type
                WHEN 1 THEN 'VEHICLE'
                WHEN 2 THEN 'PEDESTRIAN'
                WHEN 4 THEN 'CYCLIST'
            END AS class,
            SUM(CASE WHEN er.match_type = 'TP' THEN 1 ELSE 0 END) AS tp,
            SUM(CASE WHEN er.match_type = 'FN' THEN 1 ELSE 0 END) AS fn,
            ROUND(
                CAST(SUM(CASE WHEN er.match_type = 'TP' THEN 1 ELSE 0 END) AS FLOAT)
                / NULLIF(SUM(CASE WHEN er.match_type IN ('TP','FN') THEN 1 ELSE 0 END), 0),
            4) AS recall,
            ROUND(AVG(CASE WHEN er.match_type = 'TP' THEN er.sde END), 4) AS mean_sde
        FROM eval_results er
        JOIN ground_truths gt ON er.ground_truth_id = gt.id
        WHERE er.run_name = :run
          AND er.match_type IN ('TP', 'FN')
        GROUP BY difficulty, class
        ORDER BY difficulty, class
    """)

    with db.engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"run": run_name})


# ---------------------------------------------------------------------------
# 6. Performance by LiDAR point count (direct occlusion measure)
# ---------------------------------------------------------------------------

def performance_by_lidar_points(
    db: DatabaseManager, run_name: str,
) -> pd.DataFrame:
    """Bin ground truths by how many LiDAR points hit them.

    Fewer points = more occluded or farther away.  An object with
    5 LiDAR points is barely visible; one with 200 is unmistakable.
    """

    sql = text("""
        SELECT
            CASE
                WHEN gt.num_lidar_points <   5 THEN '0-4 pts (very sparse)'
                WHEN gt.num_lidar_points <  20 THEN '5-19 pts (sparse)'
                WHEN gt.num_lidar_points < 100 THEN '20-99 pts (moderate)'
                ELSE                                '100+ pts (dense)'
            END AS lidar_density,
            SUM(CASE WHEN er.match_type = 'TP' THEN 1 ELSE 0 END) AS tp,
            SUM(CASE WHEN er.match_type = 'FN' THEN 1 ELSE 0 END) AS fn,
            ROUND(
                CAST(SUM(CASE WHEN er.match_type = 'TP' THEN 1 ELSE 0 END) AS FLOAT)
                / NULLIF(SUM(CASE WHEN er.match_type IN ('TP','FN') THEN 1 ELSE 0 END), 0),
            4) AS recall,
            ROUND(AVG(CASE WHEN er.match_type = 'TP' THEN er.sde END), 4) AS mean_sde
        FROM eval_results er
        JOIN ground_truths gt ON er.ground_truth_id = gt.id
        WHERE er.run_name = :run
          AND er.match_type IN ('TP', 'FN')
        GROUP BY lidar_density
        ORDER BY lidar_density
    """)

    with db.engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"run": run_name})


# ---------------------------------------------------------------------------
# 7. Failure case: worst misses
# ---------------------------------------------------------------------------

def worst_misses(
    db: DatabaseManager, run_name: str, limit: int = 10,
) -> pd.DataFrame:
    """Close-range objects with many LiDAR points that were MISSED.

    A missed pedestrian at 10 m with 200 LiDAR points is a critical
    safety failure.  This query ranks FNs by proximity first, then
    by how visible the object was.
    """

    sql = text("""
        SELECT
            er.frame_id,
            CASE er.object_type
                WHEN 1 THEN 'VEHICLE'
                WHEN 2 THEN 'PEDESTRIAN'
                WHEN 4 THEN 'CYCLIST'
            END AS class,
            ROUND(er.gt_range, 1)  AS distance_m,
            gt.num_lidar_points    AS lidar_pts,
            gt.detection_difficulty AS difficulty
        FROM eval_results er
        JOIN ground_truths gt ON er.ground_truth_id = gt.id
        WHERE er.run_name  = :run
          AND er.match_type = 'FN'
        ORDER BY er.gt_range ASC, gt.num_lidar_points DESC
        LIMIT :lim
    """)

    with db.engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"run": run_name, "lim": limit})


# ---------------------------------------------------------------------------
# 8. Failure case: most dangerous TP errors (high positive SDE)
# ---------------------------------------------------------------------------

def most_dangerous_errors(
    db: DatabaseManager, run_name: str, limit: int = 10,
) -> pd.DataFrame:
    """TPs where the model placed the nearest surface FURTHER from
    the ego vehicle than reality (positive signed_sde).

    The car thinks it has more room than it actually does -- this is
    the most safety-critical kind of error.
    """

    sql = text("""
        SELECT
            er.frame_id,
            CASE er.object_type
                WHEN 1 THEN 'VEHICLE'
                WHEN 2 THEN 'PEDESTRIAN'
                WHEN 4 THEN 'CYCLIST'
            END AS class,
            ROUND(er.gt_range, 1)          AS distance_m,
            ROUND(er.iou, 4)               AS iou,
            ROUND(er.sde, 4)               AS sde,
            ROUND(er.signed_sde, 4)        AS signed_sde,
            ROUND(er.heading_accuracy, 4)  AS heading_acc,
            ROUND(er.confidence, 4)        AS confidence
        FROM eval_results er
        WHERE er.run_name   = :run
          AND er.match_type = 'TP'
          AND er.signed_sde > 0
        ORDER BY er.signed_sde DESC
        LIMIT :lim
    """)

    with db.engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"run": run_name, "lim": limit})


# ---------------------------------------------------------------------------
# 9. Failure case: high-confidence hallucinations
# ---------------------------------------------------------------------------

def confident_false_positives(
    db: DatabaseManager, run_name: str, limit: int = 10,
) -> pd.DataFrame:
    """False positives sorted by confidence (highest first).

    The model was very sure it saw something, but nothing was there.
    Downstream systems trust high-confidence detections and may brake
    or swerve for phantom objects.
    """

    sql = text("""
        SELECT
            er.frame_id,
            CASE er.object_type
                WHEN 1 THEN 'VEHICLE'
                WHEN 2 THEN 'PEDESTRIAN'
                WHEN 4 THEN 'CYCLIST'
            END AS class,
            ROUND(er.confidence, 4) AS confidence
        FROM eval_results er
        WHERE er.run_name   = :run
          AND er.match_type = 'FP'
        ORDER BY er.confidence DESC
        LIMIT :lim
    """)

    with db.engine.connect() as conn:
        return pd.read_sql(sql, conn, params={"run": run_name, "lim": limit})

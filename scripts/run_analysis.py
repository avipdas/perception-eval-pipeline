"""Run all SQL analytical queries and print formatted results.

Usage:
    python -m scripts.run_analysis
    python -m scripts.run_analysis --run-name waymo_v1
"""

from __future__ import annotations

import argparse

from analysis.queries import (
    confident_false_positives,
    most_dangerous_errors,
    performance_by_class,
    performance_by_difficulty,
    performance_by_distance,
    performance_by_distance_and_class,
    performance_by_lidar_points,
    summary_statistics,
    worst_misses,
)
from storage.database import DatabaseManager


def _section(title: str, df) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}")
    if df.empty:
        print("  (no data)")
    else:
        print(df.to_string(index=False))
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run analytical queries.")
    parser.add_argument(
        "--run-name", default="default",
        help="Evaluation run to analyse (default: 'default')",
    )
    args = parser.parse_args()

    db = DatabaseManager()
    run = args.run_name

    print(f"\n  Analysing evaluation run: '{run}'")

    _section("1. SUMMARY", summary_statistics(db, run))
    _section("2. PERFORMANCE BY DISTANCE", performance_by_distance(db, run))
    _section("3. PERFORMANCE BY OBJECT CLASS", performance_by_class(db, run))
    _section(
        "4. DISTANCE x CLASS (cross-tab)",
        performance_by_distance_and_class(db, run),
    )
    _section(
        "5. DETECTION DIFFICULTY (Waymo occlusion proxy)",
        performance_by_difficulty(db, run),
    )
    _section(
        "6. LiDAR POINT DENSITY (direct occlusion measure)",
        performance_by_lidar_points(db, run),
    )
    _section("7. WORST MISSES (close + visible objects that were missed)", worst_misses(db, run))
    _section("8. MOST DANGEROUS ERRORS (model thinks more room exists)", most_dangerous_errors(db, run))
    _section("9. HIGH-CONFIDENCE HALLUCINATIONS", confident_false_positives(db, run))


if __name__ == "__main__":
    main()

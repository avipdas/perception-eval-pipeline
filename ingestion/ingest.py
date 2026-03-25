"""Read Waymo TFRecords and write them into the SQL database.

This is the bridge between loader.py (which parses tfrecords into dicts)
and schema.py (which defines the database tables). It reads each frame,
creates the appropriate rows, and saves them.

Usage:
    # Ingest all .tfrecord files under data/raw/waymo/
    python -m ingestion.ingest

    # Ingest a single file
    python -m ingestion.ingest data/raw/waymo/some_segment.tfrecord

    # Only ingest 5 frames per file (fast for testing)
    python -m ingestion.ingest --max-frames 5
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ingestion.loader import load_tfrecord
from storage.database import DatabaseManager
from storage.schema import Segment, Frame, GroundTruth


def _get_or_create_segment(session, frame_dict) -> Segment:
    """Return existing segment row, or create a new one."""
    seg = (
        session.query(Segment)
        .filter(Segment.context_name == frame_dict["context_name"])
        .first()
    )
    if seg is None:
        seg = Segment(
            context_name=frame_dict["context_name"],
            location=frame_dict.get("location"),
            weather=frame_dict.get("weather"),
            time_of_day=frame_dict.get("time_of_day"),
        )
        session.add(seg)
        session.flush()
    return seg


def ingest_tfrecord(db: DatabaseManager, path: Path, max_frames: int | None = None) -> int:
    """Ingest one .tfrecord file into the database. Returns frame count."""
    count = 0
    with db.session() as session:
        for frame_dict in load_tfrecord(path):
            if max_frames is not None and count >= max_frames:
                break

            seg = _get_or_create_segment(session, frame_dict)

            frame_row = Frame(
                segment_id=seg.id,
                timestamp_micros=frame_dict["timestamp_micros"],
                frame_index=frame_dict["frame_index"],
            )
            session.add(frame_row)
            session.flush()

            for label in frame_dict["laser_labels"]:
                gt = GroundTruth(
                    frame_id=frame_row.id,
                    object_id=label["id"],
                    object_type=label["type"],
                    center_x=label["center_x"],
                    center_y=label["center_y"],
                    center_z=label["center_z"],
                    length=label["length"],
                    width=label["width"],
                    height=label["height"],
                    heading=label["heading"],
                    range=label["range"],
                    num_lidar_points=label["num_lidar_points"],
                    detection_difficulty=label["detection_difficulty"],
                    tracking_difficulty=label["tracking_difficulty"],
                    speed_x=label["speed_x"],
                    speed_y=label["speed_y"],
                )
                session.add(gt)

            count += 1

    print(f"Ingested {count} frames from {path.name}")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Waymo TFRecords into the database.")
    parser.add_argument(
        "path",
        nargs="?",
        default="data/raw/waymo",
        help="Path to a .tfrecord file or directory of them (default: data/raw/waymo)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Max frames to ingest per file (useful for testing).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate all tables before ingesting.",
    )
    args = parser.parse_args()

    db = DatabaseManager()
    if args.reset:
        print("Dropping all tables...")
        db.drop_tables()
    db.create_tables()

    target = Path(args.path)
    if target.is_file():
        ingest_tfrecord(db, target, max_frames=args.max_frames)
    elif target.is_dir():
        tfrecords = sorted(target.glob("*.tfrecord"))
        if not tfrecords:
            print(f"No .tfrecord files found in {target}")
            return
        for path in tfrecords:
            ingest_tfrecord(db, path, max_frames=args.max_frames)
    else:
        print(f"Path does not exist: {target}")


if __name__ == "__main__":
    main()

"""CLI entry point: serialize perception eval data to natural language text.

Examples
--------
# Serialize every frame in the default eval run to JSONL:
    python -m scripts.serialize_to_text

# Use a different eval run name:
    python -m scripts.serialize_to_text --run default

# Serialize a single frame and print to stdout instead of a file:
    python -m scripts.serialize_to_text --frame 3 --stdout

# Write compact JSONL (one JSON object per line, no indentation):
    python -m scripts.serialize_to_text --output data/processed/scene_texts.jsonl

# Write pretty-printed JSON (easier to read/audit):
    python -m scripts.serialize_to_text --pretty

Output
------
Default output path: data/processed/scene_texts.jsonl
Each line is a JSON object with keys:
  frame_id, segment, frame_index, timestamp_micros,
  conditions, fn_count, fp_count, tp_count, metadata, scene_text
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python -m scripts.serialize_to_text` from repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from storage.database import DatabaseManager
from llm.serialize import iter_frames, save_jsonl


DEFAULT_OUTPUT = _REPO_ROOT / "data" / "processed" / "scene_texts.jsonl"
DEFAULT_RUN    = "waymo_v1"


def iparse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Serialize 3-D perception eval results to natural language text."
    )
    p.add_argument(
        "--run",
        default=DEFAULT_RUN,
        help=f"Eval run name stored in eval_results.run_name (default: {DEFAULT_RUN!r})",
    )
    p.add_argument(
        "--frame",
        type=int,
        default=None,
        metavar="FRAME_ID",
        help="Serialize only this frame_id (database PK).  Omit to process all frames.",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output JSONL path (default: {DEFAULT_OUTPUT})",
    )
    p.add_argument(
        "--stdout",
        action="store_true",
        help="Print scene_text to stdout instead of writing a file (useful for spot-checks).",
    )
    p.add_argument(
        "--pretty",
        action="store_true",
        help="Write pretty-printed JSON (indented).  Ignored when --stdout is set.",
    )
    p.add_argument(
        "--db",
        default=None,
        metavar="URL",
        help="SQLAlchemy database URL.  Defaults to data/eval.db.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    db   = DatabaseManager(url=args.db)

    print(f"Run name : {args.run!r}")
    print(f"Database : {args.db or 'data/eval.db (default)'}")

    if args.stdout:
        print(f"Mode     : stdout (frame_id={args.frame})\n")
        for record in iter_frames(args.run, db, frame_id=args.frame):
            print("=" * 72)
            print(record.scene_text)
            print()
        return

    print(f"Output   : {args.output}")
    print(f"Frame    : {'all' if args.frame is None else args.frame}")
    print(f"Pretty   : {args.pretty}\n")

    count = save_jsonl(
        output_path=args.output,
        run_name=args.run,
        db=db,
        frame_id=args.frame,
        pretty=args.pretty,
    )

    print(f"\nDone. {count} frame(s) written → {args.output}")


if __name__ == "__main__":
    main()

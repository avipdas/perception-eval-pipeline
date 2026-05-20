"""CLI entry point for the LLM-powered perception failure triage pipeline.

Reads serialized scene text from data/processed/scene_texts.jsonl,
routes each frame through a Chain-of-Thought classification prompt,
and writes structured triage results to data/processed/triage_results.jsonl.

Examples
--------
# Full triage on all 30 frames (uses ANTHROPIC_API_KEY from env):
    python -m scripts.run_triage

# Test on 3 frames first:
    python -m scripts.run_triage --max-frames 3

# Operational Tier 1 screening only:
    python -m scripts.run_triage --mode tier1

# Technical Tier 2 deep-dive on specific frames:
    python -m scripts.run_triage --mode tier2 --frames 11 14 20

# Specify API key explicitly:
    python -m scripts.run_triage --api-key sk-ant-...

# Print one frame's result to stdout without writing a file:
    python -m scripts.run_triage --stdout --frames 1

Environment
-----------
    ANTHROPIC_API_KEY   Anthropic API key (required unless --api-key is passed)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from llm.pipeline import (
    DEFAULT_SCENE_JSONL,
    TriageMode,
    TriagePipeline,
    load_scenes,
)

DEFAULT_OUTPUT = _REPO_ROOT / "data" / "processed" / "triage_results.jsonl"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="LLM-powered perception failure triage pipeline."
    )
    p.add_argument(
        "--mode",
        choices=["full", "tier1", "tier2"],
        default="full",
        help=(
            "Triage mode: 'full' = both tiers in one pass (default), "
            "'tier1' = operational screening, 'tier2' = technical deep-dive."
        ),
    )
    p.add_argument(
        "--frames",
        type=int,
        nargs="+",
        metavar="FRAME_ID",
        default=None,
        help="Specific frame_id(s) to triage.  Omit to process all frames.",
    )
    p.add_argument(
        "--max-frames",
        type=int,
        default=None,
        metavar="N",
        help="Cap number of frames (useful for testing / cost control).",
    )
    p.add_argument(
        "--scenes",
        type=Path,
        default=DEFAULT_SCENE_JSONL,
        help=f"Path to scene_texts.jsonl (default: {DEFAULT_SCENE_JSONL})",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output JSONL path (default: {DEFAULT_OUTPUT})",
    )
    p.add_argument(
        "--pretty",
        action="store_true",
        help="Write indented JSON (easier to read).",
    )
    p.add_argument(
        "--stdout",
        action="store_true",
        help="Print results to stdout instead of writing a file.",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=0.5,
        metavar="SECONDS",
        help="Pause between API calls to avoid rate limits (default: 0.5 s).",
    )
    p.add_argument(
        "--api-key",
        default=None,
        dest="api_key",
        metavar="KEY",
        help="Anthropic API key (overrides ANTHROPIC_API_KEY env var).",
    )
    p.add_argument(
        "--model",
        default="claude-sonnet-4-5",
        help="Claude model slug (default: claude-sonnet-4-5).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Mode          : {args.mode}")
    print(f"Model         : {args.model}")
    print(f"Scenes file   : {args.scenes}")
    print(f"Frame filter  : {args.frames or 'all'}")
    print(f"Max frames    : {args.max_frames or 'unlimited'}")
    if not args.stdout:
        print(f"Output        : {args.output}")
    print()

    # Validate scenes file exists
    if not args.scenes.exists():
        print(
            f"ERROR: {args.scenes} not found.\n"
            f"Run first: python -m scripts.serialize_to_text",
            file=sys.stderr,
        )
        sys.exit(1)

    # Build pipeline
    try:
        pipe = TriagePipeline(
            api_key=args.api_key,
            model=args.model,
        )
    except EnvironmentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    # Run triage
    results = pipe.run_all(
        mode=args.mode,
        scenes_path=args.scenes,
        frame_ids=args.frames,
        max_frames=args.max_frames,
        delay_s=args.delay,
    )

    if not results:
        print("No frames processed.")
        return

    # Print rollup
    pipe.print_summary(results)

    # Output
    if args.stdout:
        for r in results:
            print(json.dumps(r.to_dict(), indent=2 if args.pretty else None))
    else:
        pipe.save_results(results, args.output, pretty=args.pretty)


if __name__ == "__main__":
    main()

"""LangChain triage pipeline.

Architecture
------------

  scene_texts.jsonl
        │
        ▼
  load_scenes()           ← reads serialized scene text from disk
        │
        ▼
  TriagePipeline          ← LangChain chains + routing logic
  ┌─────────────────────────────────────────────────────────┐
  │  Mode "full"  → TRIAGE_PROMPT  │ Claude │ JsonParser   │
  │  Mode "tier1" → TIER1_PROMPT   │ Claude │ JsonParser   │
  │  Mode "tier2" → TIER2_PROMPT   │ Claude │ JsonParser   │
  └─────────────────────────────────────────────────────────┘
        │
        ▼
  TriageResult (Pydantic)
        │
        ▼
  save_results()          ← JSONL + optional summary CSV

All three modes route to Claude claude-sonnet-4-5 (Anthropic) which provides
the reasoning quality needed to reliably classify spatial failure modes.

Usage
-----
  from llm.pipeline import TriagePipeline
  pipe = TriagePipeline()                         # reads ANTHROPIC_API_KEY from env
  results = pipe.run_all(mode="full", max_frames=5)
  pipe.save_results(results, Path("data/processed/triage_results.jsonl"))
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Literal

# Load .env from repo root (if present) before reading env vars.
# python-dotenv is a no-op when the file doesn't exist, so this is safe.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
except ImportError:
    pass  # python-dotenv not installed; rely on shell env

from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import RunnableSequence

from llm.prompts import TIER1_PROMPT, TIER2_PROMPT, TRIAGE_PROMPT
from llm.taxonomy import FAILURE_MODE_BY_CODE

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SCENE_JSONL = Path("data/processed/scene_texts.jsonl")
DEFAULT_MODEL       = "claude-sonnet-4-5"
DEFAULT_TEMPERATURE = 0.0   # deterministic — critical for reproducible triage
DEFAULT_MAX_TOKENS  = 4096

TriageMode = Literal["full", "tier1", "tier2"]


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    event_type:      str
    object_index:    int
    object_class:    str
    range_m:         float | None
    rationale:       str
    failure_code:    str | None
    tier:            int | None
    safety_severity: str | None
    confidence:      float
    # Enriched after parsing — pulled from taxonomy
    label:           str | None = None
    recommended_action: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Finding":
        code = d.get("failure_code")
        fm   = FAILURE_MODE_BY_CODE.get(code, {}) if code else {}
        return cls(
            event_type=d.get("event_type", ""),
            object_index=d.get("object_index", 0),
            object_class=d.get("object_class", "UNKNOWN"),
            range_m=d.get("range_m"),
            rationale=d.get("rationale", ""),
            failure_code=code,
            tier=d.get("tier"),
            safety_severity=d.get("safety_severity"),
            confidence=d.get("confidence", 0.0),
            label=fm.get("label"),
            recommended_action=fm.get("recommended_action"),
        )


@dataclass
class TriageResult:
    frame_id:      int
    frame_index:   int
    conditions:    str
    findings:      list[Finding]
    frame_summary: str
    mode:          TriageMode
    model:         str
    latency_s:     float
    raw_response:  dict[str, Any]
    error:         str | None = None

    # Convenience: counts by severity
    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.safety_severity == "critical")

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.safety_severity == "high")

    @property
    def tier2_count(self) -> int:
        return sum(1 for f in self.findings if f.tier == 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id":      self.frame_id,
            "frame_index":   self.frame_index,
            "conditions":    self.conditions,
            "mode":          self.mode,
            "model":         self.model,
            "latency_s":     round(self.latency_s, 3),
            "critical_count": self.critical_count,
            "high_count":    self.high_count,
            "tier2_count":   self.tier2_count,
            "frame_summary": self.frame_summary,
            "findings": [
                {
                    "event_type":       f.event_type,
                    "object_index":     f.object_index,
                    "object_class":     f.object_class,
                    "range_m":          f.range_m,
                    "failure_code":     f.failure_code,
                    "label":            f.label,
                    "tier":             f.tier,
                    "safety_severity":  f.safety_severity,
                    "confidence":       f.confidence,
                    "rationale":        f.rationale,
                    "recommended_action": f.recommended_action,
                }
                for f in self.findings
            ],
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Scene loader
# ---------------------------------------------------------------------------

def load_scenes(
    path: Path = DEFAULT_SCENE_JSONL,
    frame_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """
    Load serialized scene records from the JSONL file produced by serialize.py.

    The file may be pretty-printed (multi-line JSON objects) or compact
    (one object per line); both are handled via raw_decode.
    """
    raw = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    records, pos = [], 0
    raw = raw.lstrip()
    while pos < len(raw):
        obj, end = decoder.raw_decode(raw, pos)
        records.append(obj)
        pos = end
        while pos < len(raw) and raw[pos] in " \t\n\r":
            pos += 1

    if frame_ids is not None:
        records = [r for r in records if r["frame_id"] in frame_ids]

    return records


# ---------------------------------------------------------------------------
# Pretty-print helper
# ---------------------------------------------------------------------------

_SEV_ICON = {
    "critical":   "🔴",
    "high":       "🟠",
    "medium":     "🟡",
    "low-medium": "🟡",
    "low":        "🟢",
    "negligible": "⚪",
}


def _print_result(result: "TriageResult") -> None:
    """Print every field from to_dict() in a human-readable format."""
    sep = "  " + "─" * 68
    print(sep)
    print(f"  Frame {result.frame_index}  (frame_id={result.frame_id})")
    print(f"  Conditions : {result.conditions}")
    print(f"  Model      : {result.model}  |  latency {result.latency_s:.1f}s")
    print(f"  Counts     : critical={result.critical_count}  high={result.high_count}  "
          f"tier2={result.tier2_count}  total={len(result.findings)}")
    if result.frame_summary:
        print(f"\n  Summary    : {result.frame_summary}")

    if result.findings:
        print(f"\n  Findings:")
        for f in result.findings:
            icon = _SEV_ICON.get(f.safety_severity or "", "  ")
            tier_str = f"T{f.tier}" if f.tier else "  "
            code_str = f.failure_code or "clean TP"
            label_str = f.label or ""
            range_str = f"{f.range_m:.1f} m" if f.range_m is not None else "—"
            print(
                f"\n  {icon} [{f.event_type}] #{f.object_index} {f.object_class} "
                f"at {range_str}  |  {tier_str} {code_str}"
            )
            if label_str:
                print(f"     Label    : {label_str}")
            print(f"     Severity : {f.safety_severity or '—'}  |  "
                  f"Confidence : {f.confidence:.2f}")
            print(f"     Rationale: {f.rationale}")
            if f.recommended_action:
                print(f"     Action   : {f.recommended_action}")
    print(sep)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class TriagePipeline:
    """
    LangChain-powered triage pipeline.

    Parameters
    ----------
    api_key:
        Anthropic API key.  Falls back to ANTHROPIC_API_KEY env var.
    model:
        Claude model slug (default: claude-sonnet-4-5).
    temperature:
        0.0 for fully deterministic classifications.
    retry_on_parse_error:
        If True, retry once with a stricter "return valid JSON only" reminder
        when the response cannot be parsed.
    """

    def __init__(
        self,
        api_key:               str | None = None,
        model:                 str        = DEFAULT_MODEL,
        temperature:           float      = DEFAULT_TEMPERATURE,
        max_tokens:            int        = DEFAULT_MAX_TOKENS,
        retry_on_parse_error:  bool       = True,
    ) -> None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise EnvironmentError(
                "No Anthropic API key found.  Set ANTHROPIC_API_KEY in your "
                "environment or pass api_key= to TriagePipeline()."
            )

        self._llm = ChatAnthropic(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            anthropic_api_key=key,
        )
        self._model              = model
        self._retry              = retry_on_parse_error
        self._parser             = JsonOutputParser()
        self._chains: dict[TriageMode, RunnableSequence] = {
            "full":  TRIAGE_PROMPT  | self._llm | self._parser,
            "tier1": TIER1_PROMPT   | self._llm | self._parser,
            "tier2": TIER2_PROMPT   | self._llm | self._parser,
        }

    # ------------------------------------------------------------------
    # Single-frame classification
    # ------------------------------------------------------------------

    def classify_frame(
        self,
        scene: dict[str, Any],
        mode: TriageMode = "full",
    ) -> TriageResult:
        """Run the triage chain on one serialized scene dict."""
        chain = self._chains[mode]
        t0    = time.perf_counter()
        error = None
        raw   = {}

        try:
            raw = chain.invoke({"scene_text": scene["scene_text"]})
        except Exception as exc:
            # On parse error, retry once with an explicit JSON-only reminder
            if self._retry and "JSONDecodeError" in type(exc).__name__:
                try:
                    reminder = (
                        scene["scene_text"]
                        + "\n\nIMPORTANT: Your response must be a single valid "
                        "JSON object.  No prose, no markdown."
                    )
                    raw = chain.invoke({"scene_text": reminder})
                except Exception as exc2:
                    error = str(exc2)
                    raw   = {}
            else:
                error = str(exc)
                raw   = {}

        latency = time.perf_counter() - t0

        findings = [
            Finding.from_dict(f)
            for f in raw.get("findings", [])
        ]

        return TriageResult(
            frame_id=scene["frame_id"],
            frame_index=scene.get("frame_index", -1),
            conditions=scene.get("conditions", ""),
            findings=findings,
            frame_summary=raw.get("frame_summary", ""),
            mode=mode,
            model=self._model,
            latency_s=latency,
            raw_response=raw,
            error=error,
        )

    # ------------------------------------------------------------------
    # Batch runner
    # ------------------------------------------------------------------

    def run_all(
        self,
        mode:         TriageMode         = "full",
        scenes_path:  Path               = DEFAULT_SCENE_JSONL,
        frame_ids:    list[int] | None   = None,
        max_frames:   int | None         = None,
        delay_s:      float              = 0.5,
    ) -> list[TriageResult]:
        """
        Classify every frame in the scene JSONL.

        Parameters
        ----------
        mode:
            "full" — single pass classifying all tiers (recommended).
            "tier1" — operational screening only.
            "tier2" — technical deep-dive only.
        scenes_path:
            Path to the scene_texts.jsonl produced by serialize.py.
        frame_ids:
            If provided, only these frame_ids are processed.
        max_frames:
            Cap for testing / cost control.
        delay_s:
            Inter-request pause to avoid rate-limit errors.
        """
        scenes = load_scenes(scenes_path, frame_ids=frame_ids)
        if max_frames is not None:
            scenes = scenes[:max_frames]

        results: list[TriageResult] = []
        total = len(scenes)

        for i, scene in enumerate(scenes, 1):
            fid = scene["frame_id"]
            print(
                f"  [{i:>3}/{total}] frame_id={fid:>4}  "
                f"FN={scene.get('fn_count',0)} "
                f"FP={scene.get('fp_count',0)} "
                f"TP={scene.get('tp_count',0)}  mode={mode}",
                end=" ... ",
                flush=True,
            )
            result = self.classify_frame(scene, mode=mode)
            results.append(result)
            if result.error:
                print(f"ERROR: {result.error}")
            else:
                print(
                    f"crit={result.critical_count} high={result.high_count} "
                    f"t2={result.tier2_count} ({result.latency_s:.1f}s)"
                )
                _print_result(result)

            if i < total and delay_s > 0:
                time.sleep(delay_s)

        return results

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    @staticmethod
    def save_results(
        results:     list[TriageResult],
        output_path: Path,
        pretty:      bool = False,
    ) -> None:
        """Write triage results to JSONL."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as fh:
            for r in results:
                line = r.to_dict()
                if pretty:
                    fh.write(json.dumps(line, indent=2, ensure_ascii=False) + "\n")
                else:
                    fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        print(f"Saved {len(results)} results → {output_path}")

    @staticmethod
    def print_summary(results: list[TriageResult]) -> None:
        """Print a quick human-readable rollup to stdout."""
        from collections import Counter

        code_counts: Counter[str] = Counter()
        sev_counts:  Counter[str] = Counter()

        for r in results:
            for f in r.findings:
                if f.failure_code:
                    code_counts[f.failure_code] += 1
                if f.safety_severity:
                    sev_counts[f.safety_severity] += 1

        total_findings = sum(code_counts.values())
        total_critical = sev_counts.get("critical", 0)
        total_high     = sev_counts.get("high", 0)

        print("\n" + "=" * 60)
        print(f"TRIAGE SUMMARY  ({len(results)} frames, {total_findings} findings)")
        print("=" * 60)
        print(f"  Critical : {total_critical}")
        print(f"  High     : {total_high}")
        print(f"  Medium   : {sev_counts.get('medium', 0)}")
        print(f"  Low      : {sev_counts.get('low', 0) + sev_counts.get('low-medium', 0)}")
        print()
        print("Top failure codes:")
        for code, count in code_counts.most_common(10):
            fm = FAILURE_MODE_BY_CODE.get(code, {})
            label = fm.get("label", code)
            tier  = fm.get("tier", "?")
            print(f"  T{tier}  {count:>4}×  {code}  — {label}")
        print("=" * 60)


# ---------------------------------------------------------------------------
# Convenience function for quick single-frame tests
# ---------------------------------------------------------------------------

def triage_frame(
    frame_id:  int,
    mode:      TriageMode = "full",
    api_key:   str | None = None,
) -> TriageResult:
    """Quick helper: load one frame from the default JSONL and triage it."""
    scenes = load_scenes(frame_ids=[frame_id])
    if not scenes:
        raise ValueError(f"frame_id={frame_id} not found in {DEFAULT_SCENE_JSONL}")
    pipe = TriagePipeline(api_key=api_key)
    return pipe.classify_frame(scenes[0], mode=mode)

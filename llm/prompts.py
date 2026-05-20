"""Chain-of-Thought prompt templates for perception failure triage.

Two prompt templates, one per tier:

  TRIAGE_PROMPT   — full scene, classifies every failure event in one pass
  TIER1_PROMPT    — operational screening (fast, cheap, high volume)
  TIER2_PROMPT    — deep technical analysis (slower, richer reasoning)

Design principles (EMMA-inspired):
  1. Spatial reasoning must be grounded in the numerical values supplied in
     the scene text (bearings, ranges, LiDAR counts, SDE values, etc.).
  2. The model must write a short CoT rationale BEFORE it emits a
     classification code.  This forces it to articulate why the evidence
     maps to a particular failure mode rather than pattern-matching on
     surface-level keywords.
  3. Output is strict JSON so downstream code can parse it without heuristics.
  4. The model is prohibited from inventing failure codes outside the taxonomy.
"""

from __future__ import annotations

import json

from langchain_core.prompts import ChatPromptTemplate

from llm.taxonomy import FAILURE_MODES

# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

# Full taxonomy block embedded verbatim in every system prompt so the model
# has the complete reference during generation.
_TAXONOMY_JSON = json.dumps(
    [
        {
            "code": fm["code"],
            "tier": fm["tier"],
            "label": fm["label"],
            "description": fm["description"],
            "primary_signal": fm["primary_signal"],
            "safety_severity": fm["safety_severity"],
        }
        for fm in FAILURE_MODES
    ],
    indent=2,
)

_OUTPUT_SCHEMA = """\
Return ONLY a single valid JSON object — no markdown fences, no prose outside the JSON.
Schema:
{
  "frame_id": <int>,
  "frame_index": <int>,
  "conditions": <str>,
  "findings": [
    {
      "event_type":   "FN" | "FP" | "TP",
      "object_index": <int>,          // the [N] index from the scene text
      "object_class": "VEHICLE" | "PEDESTRIAN" | "CYCLIST" | "SIGN",
      "range_m":      <float>,
      "rationale":    <str>,          // CoT reasoning, 1-3 sentences, citing specific numbers
      "failure_code": <str>,          // EXACTLY one code from the taxonomy, or null for clean TPs
      "tier":         1 | 2 | null,
      "safety_severity": "negligible" | "low" | "low-medium" | "medium" | "high" | "critical" | null,
      "confidence":   <float 0-1>     // your confidence in this classification
    }
  ],
  "frame_summary": <str>             // 2-3 sentence overall assessment of this frame
}"""

# ---------------------------------------------------------------------------
# Full-scene triage prompt (routes all events in one pass)
# ---------------------------------------------------------------------------

_FULL_SYSTEM = """\
You are a senior perception-safety engineer at an autonomous vehicle company.
Your job is to classify each failure event in an AV perception evaluation \
scene into the predefined taxonomy below.

COORDINATE CONVENTIONS
  - All positions are in the ego-vehicle frame: +x = forward, +y = left, +z = up.
  - Bearing 0° = straight ahead; +90° = hard left; −90° = hard right; ±180° = behind.
  - signed_sde > 0 means the predicted surface is FARTHER from ego than reality \
(model underestimates proximity — dangerous).
  - signed_sde < 0 means the predicted surface is CLOSER than reality.

TAXONOMY
{taxonomy}

CHAIN-OF-THOUGHT REQUIREMENT
For every failure event (FN, FP, or problematic TP) you MUST:
  1. Identify the key numerical evidence from the scene text (range, LiDAR pts,
     confidence, signed_sde, heading_accuracy, bearing).
  2. Write a concise rationale (1-3 sentences) that CITES those numbers and
     explains which taxonomy rule they satisfy.
  3. Then emit exactly one failure_code from the taxonomy — or null if the TP
     has no notable quality issue.

STRICT RULES
  - Use ONLY the failure codes listed in the taxonomy.  Do not invent codes.
  - Do not classify a clean TP (IoU > threshold, |signed_sde| < 0.15 m,
    heading error < 45°) as a failure — set failure_code and tier to null.
  - If multiple codes could apply, choose the HIGHEST severity one.
  - Your confidence field should reflect how clearly the evidence maps to
    that code (1.0 = unambiguous, 0.5 = borderline).

{output_schema}"""

_FULL_HUMAN = """\
Classify every failure event in the scene below.

{scene_text}"""

TRIAGE_PROMPT: ChatPromptTemplate = ChatPromptTemplate.from_messages(
    [
        ("system", _FULL_SYSTEM),
        ("human", _FULL_HUMAN),
    ]
).partial(
    taxonomy=_TAXONOMY_JSON,
    output_schema=_OUTPUT_SCHEMA,
)


# ---------------------------------------------------------------------------
# Tier 1 — fast operational screening prompt
# ---------------------------------------------------------------------------

_TIER1_CODES_JSON = json.dumps(
    [
        {
            "code": fm["code"],
            "label": fm["label"],
            "primary_signal": fm["primary_signal"],
        }
        for fm in FAILURE_MODES
        if fm["tier"] == 1
    ],
    indent=2,
)

_TIER1_SYSTEM = """\
You are an automated dataset-quality screener.  Your role is ONLY to identify \
Tier 1 operational issues — annotation errors, expected range roll-off, \
below-threshold false positives, and known difficulty-level misses.

TIER 1 CODES (use ONLY these)
{tier1_codes}

CHAIN-OF-THOUGHT REQUIREMENT
For each event you classify as Tier 1:
  1. Quote the specific number(s) that triggered the rule (e.g. "3 LiDAR pts",
     "range 68.2 m", "confidence 0.21").
  2. Name the exact code it satisfies.
  3. If no Tier 1 rule applies, set failure_code to null — do NOT escalate to
     Tier 2 codes; that is handled by a separate process.

{output_schema}"""

_TIER1_HUMAN = """\
Screen the following scene for Tier 1 operational issues only.

{scene_text}"""

TIER1_PROMPT: ChatPromptTemplate = ChatPromptTemplate.from_messages(
    [
        ("system", _TIER1_SYSTEM),
        ("human", _TIER1_HUMAN),
    ]
).partial(
    tier1_codes=_TIER1_CODES_JSON,
    output_schema=_OUTPUT_SCHEMA,
)


# ---------------------------------------------------------------------------
# Tier 2 — deep technical analysis prompt
# ---------------------------------------------------------------------------

_TIER2_CODES_JSON = json.dumps(
    [
        {
            "code": fm["code"],
            "label": fm["label"],
            "description": fm["description"],
            "primary_signal": fm["primary_signal"],
            "safety_severity": fm["safety_severity"],
            "recommended_action": fm["recommended_action"],
        }
        for fm in FAILURE_MODES
        if fm["tier"] == 2
    ],
    indent=2,
)

_TIER2_SYSTEM = """\
You are a senior perception engineer conducting a deep-dive safety review.
You have already seen a Tier 1 screening; your task is to identify Tier 2 \
technical failures: near-field critical misses, vulnerable road user misses, \
depth underestimation, heading confusion, high-confidence hallucinations, and \
localization ambiguity.

COORDINATE CONVENTIONS
  - +x = forward, +y = left.  Bearing: 0° ahead, +90° hard-left, −90° hard-right.
  - signed_sde > 0 → model thinks object is FARTHER than it actually is.
  - heading_accuracy is in radians; 0.785 rad ≈ 45°.

TIER 2 CODES (use ONLY these)
{tier2_codes}

CHAIN-OF-THOUGHT REQUIREMENT
For each Tier 2 event, reason step-by-step:
  Step 1 — Identify the event type (FN / FP / problematic TP) and the object.
  Step 2 — List the critical numerical evidence: range, LiDAR pts, confidence,
            signed_sde, heading_accuracy, bearing, and object class.
  Step 3 — Match to the most severe applicable Tier 2 code.  Quote the
            threshold value that was crossed (e.g. "range 8.4 m < 20 m threshold").
  Step 4 — Assess realistic safety impact given the conditions (day/night,
            weather, object velocity).
  Step 5 — Emit the JSON entry with failure_code, tier=2, safety_severity,
            and a rationale that references all four steps concisely.

{output_schema}"""

_TIER2_HUMAN = """\
Perform a Tier 2 technical safety analysis on the following scene.

{scene_text}"""

TIER2_PROMPT: ChatPromptTemplate = ChatPromptTemplate.from_messages(
    [
        ("system", _TIER2_SYSTEM),
        ("human", _TIER2_HUMAN),
    ]
).partial(
    tier2_codes=_TIER2_CODES_JSON,
    output_schema=_OUTPUT_SCHEMA,
)

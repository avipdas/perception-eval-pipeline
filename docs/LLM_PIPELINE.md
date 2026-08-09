# LLM Perception Triage Pipeline

**Location:** `docs/LLM_PIPELINE.md`

---

## What This Is

An automated pipeline that reads autonomous vehicle perception evaluation
results from a SQLite database, converts the raw numerical data into natural
language, and routes it through Claude (Anthropic) to classify every failure
event into a predefined safety taxonomy.

The approach is inspired by Waymo's **EMMA model**, which showed that
representing 3D locations, bounding boxes, and scene state as unified natural
language text lets an LLM reason over complex spatial data the same way it
reasons over any other text.

---

## The Problem It Solves

The database stores raw floats:

```
center_x=50.72, heading=3.14, signed_sde=0.26, num_lidar_points=114
```

A human engineer looking at thousands of rows of those numbers cannot
quickly answer: *"Is this a safety-critical miss or just expected sensor
roll-off? Is this heading error a one-off or a systematic calibration bug?"*

This pipeline converts those numbers to language, then has Claude answer
exactly those questions — consistently, at scale, with auditable reasoning.

---

## End-to-End Flow

```
data/eval.db  (SQLite)
      │
      │  Step 1 — Serialize
      ▼
data/processed/scene_texts.jsonl        ← 30 frames, ~72,000 words
      │
      │  Steps 2–4 — Triage
      ▼
  LangChain Pipeline
  ┌─────────────────────────────────────────────┐
  │  Taxonomy (13 failure codes, 2 tiers)       │
  │       +                                     │
  │  Chain-of-Thought Prompt                    │
  │       +                                     │
  │  Claude claude-sonnet-4-5 (Anthropic)               │
  │       +                                     │
  │  JSON Output Parser                         │
  └─────────────────────────────────────────────┘
      │
      ▼
data/processed/triage_results.jsonl     ← structured findings per frame
```

---

## Files and What Each One Does

### Step 1 — Serialization

---

#### `llm/serialize.py`
**The core serialization engine.**

Queries the SQLite database (`data/eval.db`) and converts every numerical
field into a descriptive natural language string. Handles three event types:

- **FN (missed detections)** — ground-truth boxes the model failed to detect
- **FP (phantom predictions)** — predicted boxes with no matching ground truth
- **TP (true positives)** — matched detections, with localization quality

Key functions and what they produce:

| Function | Input | Output |
|---|---|---|
| `bearing_description(cx, cy)` | `(50.7, 16.1)` | `"directly ahead"` |
| `bearing_deg(cx, cy)` | `(50.7, 16.1)` | `+18°` |
| `heading_description(rad)` | `3.14` | `"head-on toward ego (≈180°)"` |
| `velocity_description(sx, sy)` | `(20.9, 0.1)` | `"20.9 m/s moving forward"` |
| `size_description(l, w, h, type)` | `4.8, 2.1, 1.6, 1` | `"mid-size vehicle, L 4.8m × W 2.1m × H 1.6m"` |
| `lidar_description(pts)` | `114` | `"dense (114 LiDAR pts — clearly visible)"` |
| `sde_interpretation(signed_sde)` | `+0.34` | `"CRITICAL: predicted surface is 0.34m FARTHER from ego"` |
| `serialize_frame(frame_id, ...)` | frame_id=1 | complete scene text block |
| `save_jsonl(output_path, ...)` | — | writes `scene_texts.jsonl` |

**Coordinate conventions used throughout:**
- `+x` = forward, `+y` = left, `+z` = up (Waymo vehicle frame)
- Bearing `0°` = straight ahead, `+90°` = hard left, `-90°` = hard right
- `signed_sde > 0` = model thinks object is **farther** than reality (dangerous)

---

#### `scripts/serialize_to_text.py`
**CLI entry point for Step 1.**

Wraps `llm/serialize.py` with command-line arguments. Reads from
`data/eval.db`, writes to `data/processed/scene_texts.jsonl`.

```bash
# Serialize all 30 frames
python -m scripts.serialize_to_text --pretty

# Preview one frame in terminal (no file written)
python -m scripts.serialize_to_text --stdout --frame 1
```

---

### Step 2 — Taxonomy

---

#### `llm/taxonomy.py`
**The predefined failure mode dictionary.**

Contains 13 failure codes organized into two escalation tiers. Every code
has a `description`, `primary_signal` (the rule that triggers it),
`safety_severity`, and `recommended_action`.

This file is the single source of truth — the same JSON is embedded
verbatim into every LLM prompt so Claude classifies against it directly.

**Tier 1 — Operational Triage**
High-volume issues that can be auto-screened. Usually a dataset or
sensor-physics issue, not a model defect. No engineering ticket needed.

| Code | Triggers When | Severity |
|---|---|---|
| `T1_GHOST_ANNOTATION` | FN with < 5 LiDAR points (object may not exist) | low |
| `T1_RANGE_ROLLOFF` | FN or FP beyond 60 m (expected sensor physics) | low |
| `T1_LOW_CONFIDENCE_FP` | FP with confidence < 0.35 (filtered downstream) | low |
| `T1_KNOWN_OCCLUSION_LEVEL2` | FN on Level-2 difficulty object with < 20 LiDAR pts | low-medium |
| `T1_MINOR_LOCALIZATION_OFFSET` | TP with \|signed_sde\| < 0.15 m | negligible |

**Tier 2 — Technical Triage**
Real model failures requiring an engineering investigation.

| Code | Triggers When | Severity |
|---|---|---|
| `T2_NEAR_FIELD_CRITICAL_MISS` | FN within 20 m with ≥ 10 LiDAR pts | **critical** |
| `T2_PEDESTRIAN_CYCLIST_MISS` | FN of pedestrian/cyclist with ≥ 5 LiDAR pts | **critical** |
| `T2_DEPTH_UNDERESTIMATION` | TP with signed_sde > 0.30 m (model underestimates proximity) | high |
| `T2_HEADING_CONFUSION` | TP with heading error > 45° | high |
| `T2_HIGH_CONFIDENCE_HALLUCINATION` | FP with confidence ≥ 0.70 | high |
| `T2_CLOSE_RANGE_HALLUCINATION` | FP within 25 m at any confidence | high |
| `T2_MID_RANGE_STRUCTURED_MISS` | FN at 20–55 m with ≥ 20 LiDAR pts | medium |
| `T2_LOCALIZATION_AMBIGUITY` | TP with SDE > 0.40 m despite acceptable IoU | medium |

---

### Step 3 — Prompts

---

#### `llm/prompts.py`
**Chain-of-Thought prompt templates.**

Contains three `ChatPromptTemplate` objects built with LangChain. Each
embeds the full taxonomy JSON from `taxonomy.py` into its system prompt.

**The CoT requirement** is the key design decision. Every prompt forces
Claude to write a rationale citing specific numbers *before* emitting a
classification code:

```
Step 1 — identify the event type and object
Step 2 — list the critical numbers (range, LiDAR pts, confidence, signed_sde,
          heading_accuracy, bearing)
Step 3 — match to the taxonomy code and quote the threshold crossed
Step 4 — assess safety impact given conditions
Step 5 — emit JSON
```

This makes every decision auditable. You can read exactly why Frame 1's
9 heading errors were flagged as a systematic calibration issue rather than
9 independent bugs.

Three templates are defined:

| Template | Purpose | Use case |
|---|---|---|
| `TRIAGE_PROMPT` | All tiers in one pass | Default — best quality |
| `TIER1_PROMPT` | Operational screening only | Fast/cheap bulk screening |
| `TIER2_PROMPT` | Deep technical analysis only | Safety review deep-dive |

**Output schema** (same for all three):
```json
{
  "frame_id": 1,
  "findings": [
    {
      "event_type": "TP",
      "object_class": "VEHICLE",
      "range_m": 16.8,
      "rationale": "Heading error is 57.3° (exceeds 45° threshold)...",
      "failure_code": "T2_HEADING_CONFUSION",
      "tier": 2,
      "safety_severity": "high",
      "confidence": 1.0
    }
  ],
  "frame_summary": "..."
}
```

---

### Step 4 — Orchestration

---

#### `llm/pipeline.py`
**The LangChain orchestration layer.**

Wires everything together into a runnable pipeline. The core chain is:

```python
prompt | ChatAnthropic(model="claude-sonnet-4-5") | JsonOutputParser()
```

Key classes and functions:

| Name | What it does |
|---|---|
| `TriagePipeline` | Main class. Holds the LLM + three chains (full/tier1/tier2) |
| `TriagePipeline.classify_frame()` | Runs one scene dict through the chain, returns `TriageResult` |
| `TriagePipeline.run_all()` | Batches all frames, prints progress, respects rate-limit delay |
| `TriagePipeline.save_results()` | Writes `triage_results.jsonl` |
| `TriagePipeline.print_summary()` | Prints rollup (critical/high counts, top codes) |
| `load_scenes()` | Reads `scene_texts.jsonl` (handles pretty-printed or compact JSON) |
| `Finding` | Dataclass for one classified event, enriched with taxonomy metadata |
| `TriageResult` | Dataclass for one frame's complete triage output |

Auto-loads `.env` from the repo root via `python-dotenv` so
`ANTHROPIC_API_KEY` does not need to be exported manually in the shell.

---

#### `scripts/run_triage.py`
**CLI entry point for Steps 2–4.**

```bash
# Full triage, all 30 frames
python -m scripts.run_triage

# 3-frame test (cost control)
python -m scripts.run_triage --max-frames 3 --pretty

# Operational screening only
python -m scripts.run_triage --mode tier1

# Technical deep-dive on specific frames
python -m scripts.run_triage --mode tier2 --frames 11 14 20

# Print to terminal instead of file
python -m scripts.run_triage --stdout --frames 1
```

---

### Config

---

#### `.env`
**API key storage. Gitignored — never committed.**

```
ANTHROPIC_API_KEY=sk-ant-...
```

Get a key at [console.anthropic.com](https://console.anthropic.com).
$5–$10 credit covers the full 30-frame dataset many times over.

---

## Output Files

| File | Written by | Contents |
|---|---|---|
| `data/processed/scene_texts.jsonl` | `serialize_to_text.py` | 30 scene text blocks, one JSON object per frame |
| `data/processed/triage_results.jsonl` | `run_triage.py` | Classified findings per frame with rationale, code, severity |

---

## Full 30-Frame Run Results

```
TRIAGE SUMMARY  (30 frames, 596 findings)
============================================================
  Critical : 109
  High     : 279
  Medium   :  84
  Low      : 120

Top failure codes:
  T2   211×  T2_HEADING_CONFUSION             — Heading / orientation confusion
  T2    83×  T2_MID_RANGE_STRUCTURED_MISS     — Mid-range structured-scene miss
  T1    57×  T1_LOW_CONFIDENCE_FP             — Below-threshold confidence hallucination
  T2    57×  T2_NEAR_FIELD_CRITICAL_MISS      — Near-field critical miss
  T2    52×  T2_PEDESTRIAN_CYCLIST_MISS       — Vulnerable road user miss
  T2    45×  T2_HIGH_CONFIDENCE_HALLUCINATION — High-confidence hallucination
  T1    37×  T1_RANGE_ROLLOFF                 — Expected range roll-off
  T2    22×  T2_CLOSE_RANGE_HALLUCINATION     — Close-range hallucination
  T1    19×  T1_KNOWN_OCCLUSION_LEVEL2        — Level-2 occlusion miss (expected)
  T1     9×  T1_GHOST_ANNOTATION              — Ghost / sparse annotation
```

---

### Finding 1: Heading is Broken Across the Entire Dataset

**211 instances of `T2_HEADING_CONFUSION`** — 35% of all findings, present
in every frame. The 57.3° heading error first spotted on Frame 1 is not a
fluke. It is a dataset-wide systematic failure in the heading regression,
almost certainly one root cause: a miscalibrated LiDAR-to-vehicle extrinsic
rotation or a training coordinate-convention mismatch.

**One fix resolves 211 findings.**

On Frame 1, Claude's summary captured this correctly:

> *"This frame exhibits a systematic heading estimation failure affecting all
> 9 detected vehicles (57.3° error each), indicating a likely calibration or
> model architecture issue rather than per-object failures."*

---

### Finding 2: Safety-Critical Failures

| Code | Count | What It Means |
|---|---|---|
| `T2_NEAR_FIELD_CRITICAL_MISS` | **57** | Objects within 20 m with enough LiDAR to be detected — and weren't. The category most likely to cause a collision. |
| `T2_PEDESTRIAN_CYCLIST_MISS` | **52** | Vulnerable road users missed with visible sensor returns. Zero-tolerance in any AV safety framework. |
| `T2_HIGH_CONFIDENCE_HALLUCINATION` | **45** | Model ≥ 70% confident about objects that don't exist — can trigger phantom braking or avoidance. |
| `T2_CLOSE_RANGE_HALLUCINATION` | **22** | Phantom objects within 25 m of the ego vehicle — immediate proximity risk. |

109 critical findings and 279 high-severity findings across 30 frames.
This model is not road-ready.

---

### Finding 3: Tier 1 Noise Inflating Failure Metrics

**113 Tier 1 findings** that are not model defects:

| Code | Count | Why It's Not a Model Bug |
|---|---|---|
| `T1_LOW_CONFIDENCE_FP` | 57 | Score below 0.35 — filtered by downstream consumers anyway |
| `T1_RANGE_ROLLOFF` | 37 | Physics — LiDAR point density degrades naturally beyond 60 m |
| `T1_KNOWN_OCCLUSION_LEVEL2` | 19 | Heavily occluded objects within expected recall bounds |
| `T1_GHOST_ANNOTATION` | 9 | Dataset annotation errors, not model errors |

These 113 events should be excluded from recall and precision metrics.
The model is currently being penalized for dataset quality issues.

---

### Engineering Priority Order

1. **Fix heading (1 root cause, 211 findings)** — investigate LiDAR-to-vehicle
   extrinsic calibration or training coordinate convention. One engineer, one day.
2. **Investigate 52 pedestrian/cyclist misses** — file safety-critical tickets;
   cross-check camera modality if LiDAR-camera fusion is used.
3. **Root-cause 57 near-field misses** — cluster by segment and object type
   to identify whether failures are localized or distributed.
4. **Audit 45 high-confidence hallucinations** — examine point clouds at
   predicted centres for reflective surfaces, glass, or adversarial geometry.
5. **Strip Tier 1 noise from published metrics** — recall numbers are
   artificially deflated by ~113 annotation/sensor-physics events.

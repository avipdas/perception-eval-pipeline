# Perception Eval Pipeline

<div align="center">
  <video src="https://github.com/user-attachments/assets/27f11a3b-0cff-4493-84dd-78ff113c1dbd" width="100%" autoplay loop muted playsinline>
    Your browser does not support the video tag.
  </video>

  <p><em>Interactive 3D perception evaluation dashboard — LiDAR point clouds, bounding boxes, motion vectors, and failure triage</em></p>
</div>

**An end-to-end 3D perception evaluation system for autonomous driving, from raw LiDAR to LLM-powered failure triage.**

Built on the [Waymo Open Dataset](https://waymo.com/open/), this pipeline ingests real driving data, evaluates 3D object detection quality with industry-standard metrics (AP, APH, IoU, SDE), classifies failures using Claude, and visualizes everything in an interactive 3D dashboard.

![Dashboard — Combined view with LiDAR point cloud, GT/pred bounding boxes, and evaluation overlays](pictures/Dashboard%20Combined%20view%20with%20LiDAR%20point%20cloud%20GTpred%20bounding%20boxes%20and%20evaluation%20overlays.png)

---

## Why This Exists

Autonomous driving perception systems produce thousands of 3D detections per second. When something goes wrong like a missed pedestrian, a hallucinated vehicle, or a bounding box that's 2 meters off, you need to understand *why*, *how dangerous it was*, and *how often it happens*.

This pipeline answers those questions:

| Stage | What it does |
|-------|-------------|
| **Ingest** | Parse Waymo TFRecords into a queryable database |
| **Evaluate** | Match predictions to ground truth with 3D IoU, compute AP/APH/SDE |
| **Analyze** | Slice metrics by distance, class, difficulty, LiDAR density |
| **Triage** | Classify failures into 13 taxonomic codes using Claude (chain-of-thought) |
| **Visualize** | Explore everything in an interactive 3D dashboard |

---

## Dashboard

The dashboard is the primary interface for exploring evaluation results. It renders LiDAR point clouds alongside ground truth and prediction bounding boxes in a fully interactive 3D scene.

### 3D Scene Viewer

- Full LiDAR point cloud with height-based coloring
- Color-coded bounding boxes: GT matched (blue), GT missed (yellow), pred matched (green), pred hallucination (red)
- Heading arrows with accuracy-based coloring
- Motion vectors connecting matched GT↔Pred pairs with hoverable metric tooltips
- Ego vehicle model with headlights and roof-mounted LiDAR pod
- Distance rings at 30m, 50m, 75m
- Safety corridor overlay for ego-lane analysis

![3D scene with bounding boxes, heading arrows, and distance rings](pictures/3D%20scene%20with%20bounding%20boxes%20heading%20arrows%20and%20distance%20rings.png)

### Split View with Synced Cameras

Side-by-side Ground Truth vs. Predictions view with fully synchronized camera controls — rotating, panning, or zooming one pane mirrors the other in real time.

![Split view — GT on left, Predictions on right, cameras synced](pictures/Split%20view%20GT%20on%20left%20Predictions%20on%20right%20cameras%20synced.png)

### Timeline Scrubber

Frame-by-frame playback with a quality-colored timeline. Each tick is colored on a red→yellow→green gradient based on the frame's F1-like score, computed from TP/FP/FN ratios relative to the run's min/max. Scrub, click, or use keyboard shortcuts to navigate.

![Timeline with quality-colored ticks and playback controls](pictures/Timeline%20with%20qualitycolored%20ticks%20and%20playback%20controls.png)

### Failure Browser

Three tabs surface the most critical failures across the entire run:

- **Worst Misses** — ground truth objects with the lowest IoU matches
- **Dangerous Errors** — predictions with positive signed SDE (model thinks there's more room than reality)
- **Hallucinations** — high-confidence false positives with no corresponding ground truth

Clicking any row navigates to the frame and highlights the object with an animated pointer.

![Failure browser with worst misses tab selected](pictures/Failure%20browser%20with%20worst%20misses%20tab%20selected.png)

### Metrics & PR Curves

- **Match distribution** donut chart (TP/FP/FN)
- **Recall by distance** — bucketed at 0–30m, 30–50m, 50m+
- **Mean SDE by distance** — safety-critical error distribution
- **Precision-recall curves** per class (Vehicle, Pedestrian, Cyclist)

![Metrics panel and PR curves](pictures/Metrics%20panel%20and%20PR%20curves.png)

### Object Detail Panel

Click any bounding box in 3D to inspect its full evaluation:

- IoU, confidence, heading accuracy
- SDE with signed direction (closer = dangerous)
- 3D dimensions, heading, object ID
- Match type badge (TP / FP / FN)

### Motion Vector Tooltips

Hoverable diamond markers on matched GT↔Pred pairs display:

- Speed and velocity vector
- Heading angle
- Range from ego
- LiDAR point count
- Positional offset distance
- IoU and heading accuracy
- Detection difficulty level

![Motion vector tooltip showing object metrics](pictures/Motion%20vector%20tooltip%20showing%20object%20metrics.png)

### Additional Overlays

| Feature | Description |
|---------|-------------|
| **Bird's-eye minimap** | Orthographic top-down view with range circles and box footprints |
| **Front camera** | Waymo front camera image overlay, expandable on click |
| **SDE overlay** | Floating panel with mean/max SDE and per-class breakdown |
| **GT motion trails** | Historical trajectories for tracked ground truth objects |
| **Safety corridor** | Pulsing ego-lane corridor highlighting potential collision risks |

---

## Evaluation Methodology

### 3D IoU Matching

Predictions are matched to ground truth using **greedy confidence-first matching** (consistent with Waymo/COCO evaluation protocol):

1. Sort predictions by confidence (descending)
2. For each prediction, find the highest-IoU unmatched ground truth
3. Accept the match if IoU exceeds the class threshold

| Class | IoU Threshold |
|-------|--------------|
| Vehicle | 0.7 |
| Pedestrian | 0.5 |
| Cyclist | 0.5 |

### Metrics

| Metric | Description |
|--------|-------------|
| **AP** | Average Precision — area under the precision-recall curve |
| **APH** | AP weighted by heading accuracy (Waymo's primary metric) |
| **3D IoU** | Volumetric overlap using Shapely polygon intersection + height overlap |
| **SDE** | Support Distance Error — difference in closest surface distance to ego |
| **Signed SDE** | Positive = prediction is farther from ego than GT (dangerous — overestimates free space) |

### IoU Computation

The 3D IoU is computed by:
1. Projecting rotated boxes onto the ground plane as polygons (bird's-eye view)
2. Computing polygon intersection area via Shapely
3. Computing height overlap along the Z axis
4. Combining: `IoU = (intersection_area × height_overlap) / (union_volume)`

---

## LLM Failure Triage

Evaluation metrics tell you *what* went wrong. The LLM triage pipeline tells you *why* and *what to do about it*.

### How It Works

1. **Serialize** — convert structured eval results into natural-language scene descriptions (inspired by [EMMA](https://arxiv.org/abs/2410.23262))
2. **Classify** — send scene text to Claude with a chain-of-thought prompt and a 13-code failure taxonomy
3. **Output** — structured JSON with failure code, severity, rationale, and recommended action

### Failure Taxonomy

#### Tier 1 — Operational Failures (safety-critical)

| Code | Failure Mode |
|------|-------------|
| `MISSED_VULNERABLE_ROAD_USER` | Undetected pedestrian or cyclist |
| `MISSED_VEHICLE_IN_PATH` | Undetected vehicle in ego lane |
| `DANGEROUS_LOCALIZATION` | Positive signed SDE — model overestimates free space |
| `GHOST_OBJECT_IN_PATH` | High-confidence hallucination in ego lane |
| `SEVERE_SIZE_ERROR` | Box dimensions off by >50% |

#### Tier 2 — Technical Failures

| Code | Failure Mode |
|------|-------------|
| `LOW_RECALL_DISTANT` | Missed detections beyond 50m |
| `HEADING_FLIP` | Heading error >90° |
| `SYSTEMATIC_CLASS_CONFUSION` | Consistent misclassification patterns |
| `CONFIDENCE_MISCALIBRATION` | Low-confidence TPs or high-confidence FPs |
| `SPLIT_DETECTION` | Single object fragmented into multiple predictions |
| `MERGED_DETECTION` | Multiple objects collapsed into one prediction |
| `DUPLICATE_DETECTION` | Redundant predictions on the same object |
| `PARTIAL_DETECTION` | Significant IoU shortfall on matched objects |

### Triage Modes

```bash
# Full triage (both tiers)
python -m scripts.run_triage --mode full

# Operational failures only (faster, cheaper)
python -m scripts.run_triage --mode tier1

# Technical analysis only
python -m scripts.run_triage --mode tier2
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- Waymo Open Dataset TFRecord files in `data/raw/waymo/`
- Anthropic API key (only for LLM triage)

### Setup

```bash
# Clone and enter the project
git clone <repo-url>
cd perception-eval-pipeline

# Python environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend dependencies
cd dashboard/frontend
npm install
cd ../..
```

### Run the Pipeline

```bash
# 1. Ingest Waymo TFRecords → database
python -m ingestion.ingest

# 2. Generate synthetic predictions (or plug in your own model)
python -m scripts.generate_predictions

# 3. Evaluate predictions against ground truth
python -m scripts.run_evaluation --run-name waymo_v1
```

### Launch the Dashboard

```bash
# Terminal 1 — API server
source .venv/bin/activate
cd dashboard
uvicorn api:app --reload --port 8000

# Terminal 2 — Frontend
cd dashboard/frontend
npm run dev
```

Open `http://localhost:5173` in your browser.

### Optional: LLM Triage

```bash
# Serialize eval results to natural language
python -m scripts.serialize_to_text --run waymo_v1

# Run Claude-powered failure classification
export ANTHROPIC_API_KEY=sk-ant-...
python -m scripts.run_triage --mode full
```

### Optional: SQL Analysis

```bash
# Print all analytical breakdowns to terminal
python -m scripts.run_analysis --run-name waymo_v1
```

---

## Architecture

<div align="center">
  <a href="https://mermaid.live/edit#base64:eyJjb2RlIjogIiUle2luaXQ6IHsndGhlbWUnOiAnZGFyaycsICd0aGVtZVZhcmlhYmxlcyc6IHsgJ2xpbmVDb2xvcic6ICcjOGI5NDllJyB9fX0lJVxuZ3JhcGggVERcbiAgICBURihbXCJXYXltbyBURlJlY29yZHNcbkxpREFSICsgM0QgQW5ub3RhdGlvbnNcIl0pOjo6aW5wdXRcblxuICAgIFRGIC0tPiBMW1wibG9hZGVyLnB5XG5QYXJzZSBwcm90b2J1ZnNcIl06OjpncmVlblxuICAgIEwgLS0-IElbXCJpbmdlc3QucHlcbkV4dHJhY3QgZnJhbWVzICsgR1RcIl06OjpncmVlblxuXG4gICAgSSAtLT4gREJbKFwiU1FMaXRlIERhdGFiYXNlXG5zZWdtZW50cyBcdTAwYjcgZnJhbWVzIFx1MDBiNyBncm91bmRfdHJ1dGhzXG5wcmVkaWN0aW9ucyBcdTAwYjcgZXZhbF9yZXN1bHRzXCIpXTo6OnN0b3JhZ2VcblxuICAgIERCIC0tPiBNW1wibWF0Y2hpbmcucHlcbkdyZWVkeSBJb1UgbWF0Y2hpbmdcIl06OjpyZWRcbiAgICBJT1VbXCJpb3UucHkgXHUwMGI3IHNkZS5weVxuM0QgSW9VICsgRGlzdGFuY2UgRXJyb3JcIl06OjpyZWQgLS4tPiBNXG4gICAgTSAtLT4gTUVbXCJtZXRyaWNzLnB5XG5BUCBcdTAwYjcgQVBIIFx1MDBiNyBtQVBcIl06OjpyZWRcbiAgICBNRSAtLT58d3JpdGUgcmVzdWx0c3wgREJcblxuICAgIERCIC0tPiBTRVJbXCJzZXJpYWxpemUucHlcbkV2YWwgXHUyMTkyIG5hdHVyYWwgbGFuZ3VhZ2VcIl06OjpvcmFuZ2VcbiAgICBTRVIgLS0-IFRBWFtcInRheG9ub215LnB5XG4xMyBmYWlsdXJlIGNvZGVzXCJdOjo6b3JhbmdlXG4gICAgVEFYIC0tPiBQSVBbXCJwaXBlbGluZS5weVxuQ2xhdWRlIGNoYWluLW9mLXRob3VnaHRcIl06OjpvcmFuZ2VcbiAgICBQSVAgLS0-fHdyaXRlIHRyaWFnZXwgREJcblxuICAgIERCIC0tPiBRW1wicXVlcmllcy5weVxuOSBhbmFseXRpY2FsIGJyZWFrZG93bnNcIl06OjpwdXJwbGVcblxuICAgIERCIC0tPiBBUElbXCJGYXN0QVBJXG4xMiBSRVNUIGVuZHBvaW50c1wiXTo6OnRlYWxcbiAgICBBUEkgLS0-IFVJW1wiUmVhY3QgKyBUaHJlZS5qc1xuMTUgY29tcG9uZW50cyBcdTAwYjcgM0Qgdmlld2VyXCJdOjo6dGVhbFxuXG4gICAgY2xhc3NEZWYgaW5wdXQgZmlsbDojMWE3M2U4LHN0cm9rZTojNGE5YWY1LGNvbG9yOiNmZmYsc3Ryb2tlLXdpZHRoOjJweFxuICAgIGNsYXNzRGVmIGdyZWVuIGZpbGw6IzFlNmYzZSxzdHJva2U6IzM0YTg1Myxjb2xvcjojZmZmLHN0cm9rZS13aWR0aDoycHhcbiAgICBjbGFzc0RlZiBzdG9yYWdlIGZpbGw6IzhhNmQxMixzdHJva2U6I2ZiYmMwNCxjb2xvcjojZmZmLHN0cm9rZS13aWR0aDoycHhcbiAgICBjbGFzc0RlZiByZWQgZmlsbDojYTEyZDIzLHN0cm9rZTojZWE0MzM1LGNvbG9yOiNmZmYsc3Ryb2tlLXdpZHRoOjJweFxuICAgIGNsYXNzRGVmIG9yYW5nZSBmaWxsOiNhMTRlMGEsc3Ryb2tlOiNmMjk5MDAsY29sb3I6I2ZmZixzdHJva2Utd2lkdGg6MnB4XG4gICAgY2xhc3NEZWYgcHVycGxlIGZpbGw6IzVlMzVhMCxzdHJva2U6IzljN2NkYixjb2xvcjojZmZmLHN0cm9rZS13aWR0aDoycHhcbiAgICBjbGFzc0RlZiB0ZWFsIGZpbGw6IzBlN2E2YixzdHJva2U6IzFjZThiNSxjb2xvcjojZmZmLHN0cm9rZS13aWR0aDoycHhcbiIsICJtZXJtYWlkIjogeyJ0aGVtZSI6ICJkYXJrIn19">
    <img src="https://mermaid.ink/img/JSV7aW5pdDogeyd0aGVtZSc6ICdkYXJrJywgJ3RoZW1lVmFyaWFibGVzJzogeyAnbGluZUNvbG9yJzogJyM4Yjk0OWUnIH19fSUlCmdyYXBoIFRECiAgICBURihbIldheW1vIFRGUmVjb3JkcwpMaURBUiArIDNEIEFubm90YXRpb25zIl0pOjo6aW5wdXQKCiAgICBURiAtLT4gTFsibG9hZGVyLnB5ClBhcnNlIHByb3RvYnVmcyJdOjo6Z3JlZW4KICAgIEwgLS0-IElbImluZ2VzdC5weQpFeHRyYWN0IGZyYW1lcyArIEdUIl06OjpncmVlbgoKICAgIEkgLS0-IERCWygiU1FMaXRlIERhdGFiYXNlCnNlZ21lbnRzIMK3IGZyYW1lcyDCtyBncm91bmRfdHJ1dGhzCnByZWRpY3Rpb25zIMK3IGV2YWxfcmVzdWx0cyIpXTo6OnN0b3JhZ2UKCiAgICBEQiAtLT4gTVsibWF0Y2hpbmcucHkKR3JlZWR5IElvVSBtYXRjaGluZyJdOjo6cmVkCiAgICBJT1VbImlvdS5weSDCtyBzZGUucHkKM0QgSW9VICsgRGlzdGFuY2UgRXJyb3IiXTo6OnJlZCAtLi0-IE0KICAgIE0gLS0-IE1FWyJtZXRyaWNzLnB5CkFQIMK3IEFQSCDCtyBtQVAiXTo6OnJlZAogICAgTUUgLS0-fHdyaXRlIHJlc3VsdHN8IERCCgogICAgREIgLS0-IFNFUlsic2VyaWFsaXplLnB5CkV2YWwg4oaSIG5hdHVyYWwgbGFuZ3VhZ2UiXTo6Om9yYW5nZQogICAgU0VSIC0tPiBUQVhbInRheG9ub215LnB5CjEzIGZhaWx1cmUgY29kZXMiXTo6Om9yYW5nZQogICAgVEFYIC0tPiBQSVBbInBpcGVsaW5lLnB5CkNsYXVkZSBjaGFpbi1vZi10aG91Z2h0Il06OjpvcmFuZ2UKICAgIFBJUCAtLT58d3JpdGUgdHJpYWdlfCBEQgoKICAgIERCIC0tPiBRWyJxdWVyaWVzLnB5CjkgYW5hbHl0aWNhbCBicmVha2Rvd25zIl06OjpwdXJwbGUKCiAgICBEQiAtLT4gQVBJWyJGYXN0QVBJCjEyIFJFU1QgZW5kcG9pbnRzIl06Ojp0ZWFsCiAgICBBUEkgLS0-IFVJWyJSZWFjdCArIFRocmVlLmpzCjE1IGNvbXBvbmVudHMgwrcgM0Qgdmlld2VyIl06Ojp0ZWFsCgogICAgY2xhc3NEZWYgaW5wdXQgZmlsbDojMWE3M2U4LHN0cm9rZTojNGE5YWY1LGNvbG9yOiNmZmYsc3Ryb2tlLXdpZHRoOjJweAogICAgY2xhc3NEZWYgZ3JlZW4gZmlsbDojMWU2ZjNlLHN0cm9rZTojMzRhODUzLGNvbG9yOiNmZmYsc3Ryb2tlLXdpZHRoOjJweAogICAgY2xhc3NEZWYgc3RvcmFnZSBmaWxsOiM4YTZkMTIsc3Ryb2tlOiNmYmJjMDQsY29sb3I6I2ZmZixzdHJva2Utd2lkdGg6MnB4CiAgICBjbGFzc0RlZiByZWQgZmlsbDojYTEyZDIzLHN0cm9rZTojZWE0MzM1LGNvbG9yOiNmZmYsc3Ryb2tlLXdpZHRoOjJweAogICAgY2xhc3NEZWYgb3JhbmdlIGZpbGw6I2ExNGUwYSxzdHJva2U6I2YyOTkwMCxjb2xvcjojZmZmLHN0cm9rZS13aWR0aDoycHgKICAgIGNsYXNzRGVmIHB1cnBsZSBmaWxsOiM1ZTM1YTAsc3Ryb2tlOiM5YzdjZGIsY29sb3I6I2ZmZixzdHJva2Utd2lkdGg6MnB4CiAgICBjbGFzc0RlZiB0ZWFsIGZpbGw6IzBlN2E2YixzdHJva2U6IzFjZThiNSxjb2xvcjojZmZmLHN0cm9rZS13aWR0aDoycHgK?bgColor=0d1117" alt="Architecture Diagram" />
  </a>
  <p><em>Click the diagram to edit in Mermaid Live</em></p>
</div>

---

## API Reference

| Endpoint | Description |
|----------|-------------|
| `GET /api/frames` | All frames with segment metadata |
| `GET /api/frames/{id}/point_cloud` | Binary LiDAR data (Float32: x,y,z,intensity × N) |
| `GET /api/frames/{id}/boxes` | GT + pred boxes with eval metrics and match pairing |
| `GET /api/frames/{id}/camera` | Front camera JPEG |
| `GET /api/failures?type=...` | Failure cases: `worst_misses`, `dangerous_errors`, `hallucinations` |
| `GET /api/frame_stats` | Per-frame TP/FP/FN counts |
| `GET /api/runs` | Available evaluation run names |
| `GET /api/metrics` | Aggregate metrics by class and distance |
| `GET /api/pr_curve` | Precision-recall curve data per class |
| `GET /api/triage/summary` | LLM triage severity counts per frame |
| `GET /api/triage/{frame_id}` | LLM triage findings for a specific frame |

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `←` / `p` | Previous frame |
| `→` / `n` | Next frame |
| `1` | Toggle point cloud |
| `2` | Toggle ground truth |
| `3` | Toggle predictions |
| `Esc` | Close detail panel / clear highlight |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Data** | Waymo Open Dataset, TensorFlow (TFRecord parsing), SQLite, SQLAlchemy |
| **Evaluation** | NumPy, Shapely (3D IoU), custom AP/APH/SDE implementations |
| **LLM** | Claude claude-sonnet-4-5, LangChain, structured chain-of-thought prompts |
| **Backend** | FastAPI, uvicorn |
| **Frontend** | React 19, Three.js, @react-three/fiber, @react-three/drei, Vite |
| **Analysis** | Pandas, Matplotlib |

---

## Project Structure

```
perception-eval-pipeline/
├── ingestion/          # Waymo TFRecord → SQLite
│   ├── loader.py       # Protobuf parsing
│   └── ingest.py       # CLI ingestion tool
├── evaluation/         # Core eval engine
│   ├── matching.py     # Greedy TP/FP/FN matching
│   ├── metrics.py      # AP, APH, mAP
│   ├── iou.py          # 3D IoU with Shapely
│   └── sde.py          # Support Distance Error
├── analysis/           # SQL analytical queries
│   └── queries.py      # 9 query functions → DataFrames
├── llm/                # LLM failure triage
│   ├── serialize.py    # Eval data → natural language
│   ├── taxonomy.py     # 13 failure mode codes
│   ├── prompts.py      # Chain-of-thought templates
│   └── pipeline.py     # Claude integration
├── storage/            # Database layer
│   ├── schema.py       # ORM models
│   └── database.py     # Connection management
├── scripts/            # CLI entry points
│   ├── generate_predictions.py
│   ├── run_evaluation.py
│   ├── run_analysis.py
│   ├── serialize_to_text.py
│   └── run_triage.py
├── dashboard/          # Visualization
│   ├── api.py          # FastAPI backend
│   ├── point_cloud.py  # LiDAR extraction
│   └── frontend/       # React + Three.js
│       └── src/
│           ├── App.jsx
│           ├── api.js
│           └── components/  # 15 React components
├── data/
│   ├── raw/waymo/      # TFRecord files
│   └── eval.db         # SQLite database
└── docs/
    └── LLM_PIPELINE.md
```

---

## License

This project uses the [Waymo Open Dataset](https://waymo.com/open/terms/) which is subject to Waymo's terms of use.

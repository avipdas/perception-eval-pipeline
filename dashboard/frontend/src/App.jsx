import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import SceneViewer from "./components/SceneViewer";
import FrameSelector from "./components/FrameSelector";
import ControlPanel from "./components/ControlPanel";
import FailureBrowser from "./components/FailureBrowser";
import MetricsPanel from "./components/MetricsPanel";
import PRCurve from "./components/PRCurve";
import CameraView from "./components/CameraView";
import SdeOverlay from "./components/SdeOverlay";
import Minimap from "./components/Minimap";
import ObjectDetail from "./components/ObjectDetail";
import RunMetadataStrip from "./components/RunMetadataStrip";
import { fetchFrames, fetchPointCloud, fetchBoxes, fetchRuns, fetchFrameStats } from "./api";
import "./App.css";

const TRAIL_SIZE = 5;

function getUrlParams() {
  const p = new URLSearchParams(window.location.search);
  return {
    frameId: p.has("frame") ? Number(p.get("frame")) : null,
    runName: p.get("run") || "waymo_v1",
  };
}

function setUrlParams(frameId, runName) {
  const p = new URLSearchParams();
  if (frameId != null) p.set("frame", frameId);
  if (runName && runName !== "waymo_v1") p.set("run", runName);
  const str = p.toString();
  const url = str ? `${window.location.pathname}?${str}` : window.location.pathname;
  window.history.replaceState(null, "", url);
}

function formatSessionTime(d) {
  return d.toISOString().replace("T", " ").slice(0, 19) + "Z";
}

export default function App() {
  const urlInit = getUrlParams();

  const [frames, setFrames] = useState([]);
  const [frameId, setFrameId] = useState(null);
  const [pointCloudData, setPointCloudData] = useState(null);
  const [boxes, setBoxes] = useState(null);
  const [loading, setLoading] = useState(false);

  const [showPointCloud, setShowPointCloud] = useState(true);
  const [showGt, setShowGt] = useState(true);
  const [showPred, setShowPred] = useState(true);
  const [filterTypes, setFilterTypes] = useState(null);
  const [filterMatch, setFilterMatch] = useState(null);
  const [highlightId, setHighlightId] = useState(null);

  const [runName, setRunName] = useState(urlInit.runName);
  const [runs, setRuns] = useState([]);
  const [trailBuffer, setTrailBuffer] = useState([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const [viewMode, setViewMode] = useState("both");
  const [showCorridor, setShowCorridor] = useState(false);
  const [selectedBox, setSelectedBox] = useState(null);
  const [frameStats, setFrameStats] = useState({});

  const [showDistanceRings, setShowDistanceRings] = useState(true);
  const [showTrails, setShowTrails] = useState(true);
  const [showMotionVectors, setShowMotionVectors] = useState(true);
  const [showMinimap, setShowMinimap] = useState(true);

  const [sessionStartedAt] = useState(() => formatSessionTime(new Date()));

  const canvasRef = useRef(null);
  /** Monotonic id so out-of-order point cloud / box responses never overwrite the current frame. */
  const fetchSeqRef = useRef(0);

  const currentFrame = useMemo(
    () => frames.find((f) => f.id === frameId) ?? null,
    [frames, frameId]
  );

  useEffect(() => {
    fetchRuns().then(setRuns).catch(() => setRuns(["waymo_v1"]));
  }, []);

  useEffect(() => {
    fetchFrames().then((data) => {
      setFrames(data);
      const initial = urlInit.frameId && data.find((f) => f.id === urlInit.frameId)
        ? urlInit.frameId
        : data.length > 0 ? data[0].id : null;
      setFrameId(initial);
    });
  }, []);

  useEffect(() => {
    fetchFrameStats(runName)
      .then((stats) => setFrameStats((prev) => ({ ...prev, ...stats })))
      .catch(() => {});
  }, [runName]);

  useEffect(() => {
    if (frameId == null) return;
    const seq = ++fetchSeqRef.current;
    let cancelled = false;
    setLoading(true);
    setSelectedBox(null);

    let pending = 2;
    const finishOne = () => {
      pending -= 1;
      if (pending <= 0 && !cancelled && seq === fetchSeqRef.current) {
        setLoading(false);
      }
    };

    const applyIfCurrent = () => !cancelled && seq === fetchSeqRef.current;

    fetchPointCloud(frameId)
      .then((pc) => {
        if (!applyIfCurrent()) return;
        setPointCloudData({ ...pc, frameId, loadSeq: seq });
      })
      .catch((err) => {
        console.error("Point cloud:", err);
        if (applyIfCurrent()) {
          setPointCloudData({
            buffer: new Float32Array(0),
            count: 0,
            frameId,
            loadSeq: seq,
          });
        }
      })
      .finally(finishOne);

    fetchBoxes(frameId, runName)
      .then((bx) => {
        if (!applyIfCurrent()) return;
        setBoxes(bx);
        setTrailBuffer((prev) => [...prev, bx].slice(-TRAIL_SIZE));
        if (bx) {
          const tp = bx.filter((b) => b.match_type === "TP").length;
          const fp = bx.filter((b) => b.match_type === "FP").length;
          const fn = bx.filter((b) => b.match_type === "FN").length;
          setFrameStats((prev) => ({ ...prev, [frameId]: { tp, fp, fn } }));
        }
      })
      .catch((err) => console.error("Boxes:", err))
      .finally(finishOne);

    return () => {
      cancelled = true;
    };
  }, [frameId, runName]);

  useEffect(() => {
    setUrlParams(frameId, runName);
  }, [frameId, runName]);

  const handleSelectFrame = useCallback((idOrFn, highlightObjectId) => {
    if (typeof idOrFn === "function") {
      setFrameId((prev) => {
        const next = idOrFn(prev);
        setHighlightId(null);
        return next;
      });
      return;
    }
    setFrameId(idOrFn);
    setHighlightId(highlightObjectId !== undefined ? highlightObjectId : null);
  }, []);

  const handleSelectBox = useCallback((box) => {
    setSelectedBox((prev) => (prev?.object_id === box.object_id && prev?.source === box.source) ? null : box);
  }, []);

  useEffect(() => {
    const handler = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT" || e.target.tagName === "TEXTAREA") return;
      const idx = frames.findIndex((f) => f.id === frameId);
      switch (e.key) {
        case "ArrowRight":
        case "n":
          e.preventDefault();
          if (idx < frames.length - 1) handleSelectFrame(frames[idx + 1].id);
          break;
        case "ArrowLeft":
        case "p":
          e.preventDefault();
          if (idx > 0) handleSelectFrame(frames[idx - 1].id);
          break;
        case "1":
          setShowPointCloud((v) => !v);
          break;
        case "2":
          setShowGt((v) => !v);
          break;
        case "3":
          setShowPred((v) => !v);
          break;
        case "Escape":
          setSelectedBox(null);
          setHighlightId(null);
          break;
        default:
          break;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [frames, frameId, handleSelectFrame]);

  const handleScreenshot = useCallback(() => {
    const canvas = document.querySelector("canvas");
    if (!canvas) return;
    const link = document.createElement("a");
    link.download = `perception-frame-${frameId}.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
  }, [frameId]);

  const stats = boxes
    ? {
        gt: boxes.filter((b) => b.source === "gt").length,
        pred: boxes.filter((b) => b.source === "pred").length,
        tp: boxes.filter((b) => b.match_type === "TP").length,
        fp: boxes.filter((b) => b.match_type === "FP").length,
        fn: boxes.filter((b) => b.match_type === "FN").length,
      }
    : null;

  const pointCloudMountKey =
    frameId != null
      ? `pc-f${frameId}-s${pointCloudData?.loadSeq ?? "pending"}`
      : "pc-none";

  const sceneProps = {
    pointCloudData,
    pointCloudMountKey,
    showPointCloud,
    filterTypes,
    filterMatch,
    highlightId,
    trailBuffer,
    showCorridor,
    showDistanceRings,
    showTrails,
    showMotionVectors,
    onSelectBox: handleSelectBox,
    selectedBoxId: selectedBox?.object_id ?? null,
  };

  const isSplit = viewMode === "split";

  const sceneChrome = (
    <>
      <div className={`load-progress ${loading ? "load-progress-active" : ""}`} aria-hidden />
      <RunMetadataStrip
        runName={runName}
        frame={currentFrame}
        loading={loading}
        sessionStartedAt={sessionStartedAt}
      />
    </>
  );

  return (
    <div className="app">
      {!isSplit ? (
        <div className="scene-container">
          {sceneChrome}
          <SceneViewer
            ref={canvasRef}
            {...sceneProps}
            boxes={boxes}
            showGt={showGt}
            showPred={showPred}
          />
          <CameraView frameId={frameId} />
          <SdeOverlay boxes={boxes} />
          {showMinimap && <Minimap boxes={boxes} />}

          <div className="view-toolbar">
            <button type="button" className={`view-btn ${viewMode === "both" ? "active" : ""}`} onClick={() => setViewMode("both")}>Combined</button>
            <button type="button" className={`view-btn ${viewMode === "split" ? "active" : ""}`} onClick={() => setViewMode("split")}>Split</button>
          </div>

          <button
            type="button"
            className="sidebar-toggle"
            onClick={() => setSidebarOpen((v) => !v)}
            title={sidebarOpen ? "Hide sidebar" : "Show sidebar"}
          >
            {sidebarOpen ? "▶" : "◀"}
          </button>

          <ObjectDetail box={selectedBox} onClose={() => setSelectedBox(null)} />

          {stats && (
            <div className={`stats-bar tabular-nums ${loading ? "stats-bar-loading" : ""}`}>
              <span>Points: {pointCloudData?.count?.toLocaleString() ?? "—"}</span>
              <span>GT: {stats.gt}</span>
              <span className="tp">TP: {stats.tp}</span>
              <span className="fp">FP: {stats.fp}</span>
              <span className="fn">FN: {stats.fn}</span>
              <button type="button" className="screenshot-btn" onClick={handleScreenshot} title="Save screenshot (PNG)">
                Screenshot
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="split-container">
          {sceneChrome}
          <div className="split-pane">
            <span className="split-label split-label-gt">Ground Truth</span>
            <SceneViewer
              {...sceneProps}
              boxes={boxes}
              showGt={true}
              showPred={false}
            />
          </div>
          <div className="split-pane">
            <span className="split-label split-label-pred">Predictions</span>
            <SceneViewer
              {...sceneProps}
              boxes={boxes}
              showGt={false}
              showPred={true}
            />
          </div>

          <div className="view-toolbar">
            <button type="button" className={`view-btn ${viewMode === "both" ? "active" : ""}`} onClick={() => setViewMode("both")}>Combined</button>
            <button type="button" className={`view-btn ${viewMode === "split" ? "active" : ""}`} onClick={() => setViewMode("split")}>Split</button>
          </div>

          <button
            type="button"
            className="sidebar-toggle"
            onClick={() => setSidebarOpen((v) => !v)}
            title={sidebarOpen ? "Hide sidebar" : "Show sidebar"}
          >
            {sidebarOpen ? "▶" : "◀"}
          </button>
        </div>
      )}

      <div className={`sidebar ${sidebarOpen ? "" : "collapsed"}`}>
        <div className="sidebar-header">
          <h2>Perception Eval</h2>
          {runs.length > 1 && (
            <select
              className="run-select"
              value={runName}
              onChange={(e) => {
                setRunName(e.target.value);
                setTrailBuffer([]);
              }}
            >
              {runs.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          )}
        </div>
        <FrameSelector
          frames={frames}
          currentId={frameId}
          onChange={handleSelectFrame}
          loading={loading}
          frameStats={frameStats}
        />
        <ControlPanel
          showPointCloud={showPointCloud}
          setShowPointCloud={setShowPointCloud}
          showGt={showGt}
          setShowGt={setShowGt}
          showPred={showPred}
          setShowPred={setShowPred}
          filterTypes={filterTypes}
          setFilterTypes={setFilterTypes}
          filterMatch={filterMatch}
          setFilterMatch={setFilterMatch}
          showDistanceRings={showDistanceRings}
          setShowDistanceRings={setShowDistanceRings}
          showTrails={showTrails}
          setShowTrails={setShowTrails}
          showMotionVectors={showMotionVectors}
          setShowMotionVectors={setShowMotionVectors}
          showCorridor={showCorridor}
          setShowCorridor={setShowCorridor}
          showMinimap={showMinimap}
          setShowMinimap={setShowMinimap}
        />
        <MetricsPanel runName={runName} />
        <PRCurve runName={runName} />
        <FailureBrowser onSelectFrame={handleSelectFrame} runName={runName} />

        <div className="panel shortcuts-panel">
          <h3>Keyboard Shortcuts</h3>
          <div className="shortcut-grid">
            <kbd>←</kbd><span>Prev frame</span>
            <kbd>→</kbd><span>Next frame</span>
            <kbd>1</kbd><span>Toggle points</span>
            <kbd>2</kbd><span>Toggle GT</span>
            <kbd>3</kbd><span>Toggle preds</span>
            <kbd>Esc</kbd><span>Close detail / clear highlight</span>
          </div>
        </div>
      </div>
    </div>
  );
}

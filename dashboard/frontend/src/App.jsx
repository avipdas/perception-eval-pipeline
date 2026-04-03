import { useEffect, useState, useCallback, useRef } from "react";
import SceneViewer from "./components/SceneViewer";
import FrameSelector from "./components/FrameSelector";
import ControlPanel from "./components/ControlPanel";
import FailureBrowser from "./components/FailureBrowser";
import MetricsPanel from "./components/MetricsPanel";
import PRCurve from "./components/PRCurve";
import CameraView from "./components/CameraView";
import { fetchFrames, fetchPointCloud, fetchBoxes, fetchRuns } from "./api";
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

  const canvasRef = useRef(null);

  // Load available runs
  useEffect(() => {
    fetchRuns().then(setRuns).catch(() => setRuns(["waymo_v1"]));
  }, []);

  // Load frame list
  useEffect(() => {
    fetchFrames().then((data) => {
      setFrames(data);
      const initial = urlInit.frameId && data.find((f) => f.id === urlInit.frameId)
        ? urlInit.frameId
        : data.length > 0 ? data[0].id : null;
      setFrameId(initial);
    });
  }, []);

  // Load frame data
  useEffect(() => {
    if (frameId == null) return;
    let cancelled = false;
    setLoading(true);
    setPointCloudData(null);
    setBoxes(null);

    Promise.all([fetchPointCloud(frameId), fetchBoxes(frameId, runName)])
      .then(([pc, bx]) => {
        if (cancelled) return;
        setPointCloudData(pc);
        setBoxes(bx);
        setTrailBuffer((prev) => {
          const next = [...prev, bx].slice(-TRAIL_SIZE);
          return next;
        });
      })
      .catch((err) => console.error("Failed to load frame:", err))
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [frameId, runName]);

  // URL state sync
  useEffect(() => {
    setUrlParams(frameId, runName);
  }, [frameId, runName]);

  // Frame change handler -- supports callback form for playback timer
  const handleSelectFrame = useCallback(
    (idOrFn) => {
      if (typeof idOrFn === "function") {
        setFrameId((prev) => {
          const next = idOrFn(prev);
          setHighlightId(null);
          return next;
        });
      } else {
        setFrameId(idOrFn);
        setHighlightId(null);
      }
    },
    []
  );

  // Keyboard shortcuts
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
        default:
          break;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [frames, frameId, handleSelectFrame]);

  // Screenshot
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

  return (
    <div className="app">
      <div className="scene-container">
        {loading && (
          <div className="loading-overlay">
            <div className="spinner" />
            <span>Loading point cloud...</span>
          </div>
        )}
        <SceneViewer
          ref={canvasRef}
          pointCloudData={pointCloudData}
          boxes={boxes}
          showPointCloud={showPointCloud}
          showGt={showGt}
          showPred={showPred}
          filterTypes={filterTypes}
          filterMatch={filterMatch}
          highlightId={highlightId}
          trailBuffer={trailBuffer}
        />
        <CameraView frameId={frameId} />
        {stats && (
          <div className="stats-bar">
            <span>Points: {pointCloudData?.count?.toLocaleString() ?? "—"}</span>
            <span>GT: {stats.gt}</span>
            <span className="tp">TP: {stats.tp}</span>
            <span className="fp">FP: {stats.fp}</span>
            <span className="fn">FN: {stats.fn}</span>
            <button className="screenshot-btn" onClick={handleScreenshot} title="Save screenshot (PNG)">
              📷 Screenshot
            </button>
          </div>
        )}
      </div>

      <div className="sidebar">
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
        />
        <MetricsPanel runName={runName} />
        <PRCurve runName={runName} />
        <FailureBrowser onSelectFrame={handleSelectFrame} />

        <div className="panel shortcuts-panel">
          <h3>Keyboard Shortcuts</h3>
          <div className="shortcut-grid">
            <kbd>←</kbd><span>Prev frame</span>
            <kbd>→</kbd><span>Next frame</span>
            <kbd>1</kbd><span>Toggle points</span>
            <kbd>2</kbd><span>Toggle GT</span>
            <kbd>3</kbd><span>Toggle preds</span>
          </div>
        </div>
      </div>
    </div>
  );
}

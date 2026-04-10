const MATCH_TYPES = ["TP", "FP", "FN"];
const OBJECT_TYPES = [
  { value: 1, label: "Vehicle" },
  { value: 2, label: "Pedestrian" },
  { value: 4, label: "Cyclist" },
];

export default function ControlPanel({
  showPointCloud,
  setShowPointCloud,
  showGt,
  setShowGt,
  showPred,
  setShowPred,
  filterTypes,
  setFilterTypes,
  filterMatch,
  setFilterMatch,
  showDistanceRings,
  setShowDistanceRings,
  showTrails,
  setShowTrails,
  showMotionVectors,
  setShowMotionVectors,
  showCorridor,
  setShowCorridor,
  showMinimap,
  setShowMinimap,
}) {
  const toggleType = (val) => {
    if (filterTypes === null) {
      setFilterTypes(OBJECT_TYPES.map((t) => t.value).filter((v) => v !== val));
    } else if (filterTypes.includes(val)) {
      const next = filterTypes.filter((v) => v !== val);
      setFilterTypes(next.length === 0 ? null : next);
    } else {
      const next = [...filterTypes, val];
      setFilterTypes(
        next.length === OBJECT_TYPES.length ? null : next
      );
    }
  };

  const toggleMatch = (val) => {
    if (filterMatch === null) {
      setFilterMatch(MATCH_TYPES.filter((m) => m !== val));
    } else if (filterMatch.includes(val)) {
      const next = filterMatch.filter((m) => m !== val);
      setFilterMatch(next.length === 0 ? null : next);
    } else {
      const next = [...filterMatch, val];
      setFilterMatch(next.length === MATCH_TYPES.length ? null : next);
    }
  };

  const isTypeActive = (val) => filterTypes === null || filterTypes.includes(val);
  const isMatchActive = (val) => filterMatch === null || filterMatch.includes(val);

  return (
    <div className="panel">
      <h3>Layers</h3>
      <label className="toggle" title="Keyboard: 1">
        <input type="checkbox" checked={showPointCloud} onChange={() => setShowPointCloud(!showPointCloud)} />
        Point Cloud
      </label>
      <label className="toggle" title="Keyboard: 2">
        <input type="checkbox" checked={showGt} onChange={() => setShowGt(!showGt)} />
        Ground Truth
      </label>
      <label className="toggle" title="Keyboard: 3">
        <input type="checkbox" checked={showPred} onChange={() => setShowPred(!showPred)} />
        Predictions
      </label>

      <h3>3D Overlays</h3>
      <p className="panel-hint">Declutter the scene; metrics unchanged.</p>
      <label className="toggle">
        <input type="checkbox" checked={showDistanceRings} onChange={() => setShowDistanceRings(!showDistanceRings)} />
        Distance rings
      </label>
      <label className="toggle">
        <input type="checkbox" checked={showTrails} onChange={() => setShowTrails(!showTrails)} />
        GT motion trails
      </label>
      <label className="toggle">
        <input type="checkbox" checked={showMotionVectors} onChange={() => setShowMotionVectors(!showMotionVectors)} />
        TP offset vectors
      </label>
      <label className="toggle">
        <input type="checkbox" checked={showCorridor} onChange={() => setShowCorridor(!showCorridor)} />
        Safety corridor
      </label>
      <label className="toggle">
        <input type="checkbox" checked={showMinimap} onChange={() => setShowMinimap(!showMinimap)} />
        Bird&apos;s-eye minimap
      </label>

      <h3>Object Type</h3>
      <div className="chip-row">
        {OBJECT_TYPES.map((t) => (
          <button
            key={t.value}
            className={`chip ${isTypeActive(t.value) ? "active" : ""}`}
            onClick={() => toggleType(t.value)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <h3>Match Result</h3>
      <div className="chip-row">
        {MATCH_TYPES.map((m) => (
          <button
            key={m}
            className={`chip match-${m.toLowerCase()} ${isMatchActive(m) ? "active" : ""}`}
            onClick={() => toggleMatch(m)}
          >
            {m}
          </button>
        ))}
      </div>

      <div className="legend">
        <h3>Legend</h3>
        <div><span className="dot dot-tp" /> GT — matched (TP)</div>
        <div><span className="dot dot-fn" /> GT — missed (FN)</div>
        <div><span className="dot dot-pred-tp" /> Pred — matched (TP)</div>
        <div><span className="dot dot-fp" /> Pred — hallucination (FP)</div>
      </div>
    </div>
  );
}

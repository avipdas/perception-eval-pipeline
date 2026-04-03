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
      <label className="toggle">
        <input
          type="checkbox"
          checked={showPointCloud}
          onChange={() => setShowPointCloud(!showPointCloud)}
        />
        Point Cloud
      </label>
      <label className="toggle">
        <input
          type="checkbox"
          checked={showGt}
          onChange={() => setShowGt(!showGt)}
        />
        Ground Truth
      </label>
      <label className="toggle">
        <input
          type="checkbox"
          checked={showPred}
          onChange={() => setShowPred(!showPred)}
        />
        Predictions
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
        <div><span className="dot" style={{background:"#22c55e"}} /> GT — matched (TP)</div>
        <div><span className="dot" style={{background:"#eab308"}} /> GT — missed (FN)</div>
        <div><span className="dot" style={{background:"#3b82f6"}} /> Pred — matched (TP)</div>
        <div><span className="dot" style={{background:"#ef4444"}} /> Pred — hallucination (FP)</div>
      </div>
    </div>
  );
}

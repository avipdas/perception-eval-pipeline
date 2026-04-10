import { useMemo } from "react";

const TYPE_NAMES = { 1: "Vehicle", 2: "Pedestrian", 4: "Cyclist" };

export default function SdeOverlay({ boxes }) {
  const metrics = useMemo(() => {
    if (!boxes || boxes.length === 0) return null;
    const tps = boxes.filter((b) => b.match_type === "TP" && b.sde != null);
    if (tps.length === 0) return null;

    const overall = {
      count: tps.length,
      mean: tps.reduce((s, b) => s + b.sde, 0) / tps.length,
      max: Math.max(...tps.map((b) => b.sde)),
      dangerous: tps.filter((b) => b.signed_sde != null && b.signed_sde > 0).length,
    };

    const byType = {};
    tps.forEach((b) => {
      const k = b.object_type;
      if (!byType[k]) byType[k] = [];
      byType[k].push(b);
    });

    const perType = Object.entries(byType).map(([type, arr]) => ({
      type: Number(type),
      name: TYPE_NAMES[type] || "Other",
      count: arr.length,
      mean: arr.reduce((s, b) => s + b.sde, 0) / arr.length,
    }));
    perType.sort((a, b) => a.type - b.type);

    return { overall, perType };
  }, [boxes]);

  if (!metrics) return null;
  const { overall, perType } = metrics;
  const maxBar = Math.max(overall.mean, ...perType.map((p) => p.mean), 0.01);

  return (
    <div className="sde-overlay">
      <div className="sde-header">
        <span className="sde-title">SDE</span>
        <span
          className="sde-badge"
          data-level={overall.mean < 0.3 ? "ok" : overall.mean < 1 ? "warn" : "danger"}
        >
          {overall.mean < 0.3 ? "LOW" : overall.mean < 1 ? "MED" : "HIGH"}
        </span>
      </div>
      <div className="sde-stats">
        <div className="sde-stat">
          <span className="sde-val">{overall.mean.toFixed(3)}</span>
          <span className="sde-label">Mean (m)</span>
        </div>
        <div className="sde-stat">
          <span className="sde-val">{overall.max.toFixed(3)}</span>
          <span className="sde-label">Max (m)</span>
        </div>
        <div className="sde-stat">
          <span className="sde-val sde-danger">{overall.dangerous}</span>
          <span className="sde-label">Dangerous</span>
        </div>
      </div>
      <div className="sde-bars">
        {perType.map((p) => (
          <div key={p.type} className="sde-bar-row">
            <span className="sde-bar-name">{p.name}</span>
            <div className="sde-bar-track">
              <div
                className="sde-bar-fill"
                style={{ width: `${Math.min(100, (p.mean / maxBar) * 100)}%` }}
              />
            </div>
            <span className="sde-bar-val">{p.mean.toFixed(3)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

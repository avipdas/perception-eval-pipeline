import { useEffect, useState } from "react";
import { fetchMetrics } from "../api";

function DonutChart({ data }) {
  if (!data || data.length === 0) return null;
  const total = { tp: 0, fp: 0, fn: 0 };
  data.forEach((d) => { total.tp += d.tp; total.fp += d.fp; total.fn += d.fn; });
  const sum = total.tp + total.fp + total.fn;
  if (sum === 0) return null;

  const segments = [
    { key: "tp", val: total.tp, color: "#00e5ff" },
    { key: "fp", val: total.fp, color: "#ff5252" },
    { key: "fn", val: total.fn, color: "#ffc107" },
  ];

  let cumAngle = 0;
  const r = 36, cx = 50, cy = 50, ir = 22;

  return (
    <div className="chart-block">
      <h4>Match distribution</h4>
      <svg viewBox="0 0 100 100" width="120" height="120" className="chart-svg">
        {segments.map((seg) => {
          const frac = seg.val / sum;
          const angle = frac * 2 * Math.PI;
          const x1 = cx + r * Math.cos(cumAngle);
          const y1 = cy + r * Math.sin(cumAngle);
          const x2 = cx + r * Math.cos(cumAngle + angle);
          const y2 = cy + r * Math.sin(cumAngle + angle);
          const ix1 = cx + ir * Math.cos(cumAngle);
          const iy1 = cy + ir * Math.sin(cumAngle);
          const ix2 = cx + ir * Math.cos(cumAngle + angle);
          const iy2 = cy + ir * Math.sin(cumAngle + angle);
          const large = frac > 0.5 ? 1 : 0;
          const d = `M${ix1},${iy1} L${x1},${y1} A${r},${r} 0 ${large} 1 ${x2},${y2} L${ix2},${iy2} A${ir},${ir} 0 ${large} 0 ${ix1},${iy1}`;
          cumAngle += angle;
          return <path key={seg.key} d={d} fill={seg.color} opacity={0.92} />;
        })}
        <text x={cx} y={cy - 3} textAnchor="middle" fill="var(--text-primary)" fontSize="10" fontWeight="bold" className="chart-mono">{sum}</text>
        <text x={cx} y={cy + 8} textAnchor="middle" fill="var(--text-dim)" fontSize="6" className="chart-mono">total</text>
      </svg>
      <div className="chart-legend-row chart-mono">
        {segments.map((s) => (
          <span key={s.key} style={{ color: s.color, fontSize: 11 }}>
            {s.key.toUpperCase()}: {s.val}
          </span>
        ))}
      </div>
      <p className="chart-footnote">Counts of TP / FP / FN across all frames in this run (eval_results).</p>
    </div>
  );
}

function RecallByDistance({ data }) {
  if (!data || data.length === 0) return null;
  const bars = data.map((d) => ({
    label: d.d,
    recall: d.tp + d.fn > 0 ? d.tp / (d.tp + d.fn) : 0,
  }));
  const maxR = Math.max(...bars.map((b) => b.recall), 0.01);

  return (
    <div className="chart-block">
      <h4>Recall by distance</h4>
      <div className="bar-chart">
        {bars.map((b) => (
          <div key={b.label} className="bar-col">
            <div className="bar-val chart-mono">{(b.recall * 100).toFixed(0)}%</div>
            <div className="bar-track">
              <div className="bar-fill bar-fill-flat" style={{ height: `${(b.recall / maxR) * 100}%` }} />
            </div>
            <div className="bar-label chart-mono">{b.label}m</div>
          </div>
        ))}
      </div>
      <p className="chart-footnote">Recall = TP ÷ (TP + FN) per distance bucket.</p>
    </div>
  );
}

function SDEByDistance({ data }) {
  if (!data || data.length === 0) return null;
  const bars = data.filter((d) => d.sde != null).map((d) => ({
    label: d.d,
    sde: d.sde,
  }));
  if (bars.length === 0) return null;
  const maxS = Math.max(...bars.map((b) => b.sde), 0.01);

  return (
    <div className="chart-block">
      <h4>Mean SDE by distance</h4>
      <div className="bar-chart">
        {bars.map((b) => (
          <div key={b.label} className="bar-col">
            <div className="bar-val chart-mono">{b.sde.toFixed(2)}m</div>
            <div className="bar-track">
              <div className="bar-fill bar-fill-flat bar-fill-sde" style={{ height: `${(b.sde / maxS) * 100}%` }} />
            </div>
            <div className="bar-label chart-mono">{b.label}m</div>
          </div>
        ))}
      </div>
      <p className="chart-footnote">Mean support-distance error on true positives only, by GT range.</p>
    </div>
  );
}

export default function MetricsPanel({ runName }) {
  const [metrics, setMetrics] = useState(null);

  useEffect(() => {
    fetchMetrics(runName).then(setMetrics).catch(() => setMetrics(null));
  }, [runName]);

  if (!metrics) return null;

  return (
    <div className="panel metrics-panel">
      <h3>Metrics</h3>
      <DonutChart data={metrics.by_class} />
      <RecallByDistance data={metrics.by_distance} />
      <SDEByDistance data={metrics.by_distance} />
    </div>
  );
}

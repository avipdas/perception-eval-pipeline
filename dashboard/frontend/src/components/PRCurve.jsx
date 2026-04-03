import { useEffect, useState } from "react";
import { fetchPRCurve } from "../api";

const CLASS_COLORS = {
  VEHICLE: "#3b82f6",
  PEDESTRIAN: "#f97316",
  CYCLIST: "#a855f7",
};

const W = 260, H = 180, PAD = 30;

function toSvg(r, p) {
  return [PAD + r * (W - 2 * PAD), PAD + (1 - p) * (H - 2 * PAD)];
}

export default function PRCurve({ runName }) {
  const [curves, setCurves] = useState(null);
  const [hover, setHover] = useState(null);

  useEffect(() => {
    fetchPRCurve(runName).then(setCurves).catch(() => setCurves(null));
  }, [runName]);

  if (!curves) return null;

  const entries = Object.entries(curves).filter(([, pts]) => pts.length > 0);
  if (entries.length === 0) return null;

  return (
    <div className="panel pr-panel">
      <h3>Precision–Recall</h3>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        style={{ maxWidth: W }}
        onMouseLeave={() => setHover(null)}
      >
        {/* grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((v) => {
          const [, y] = toSvg(0, v);
          const [x2] = toSvg(1, v);
          return (
            <g key={`h${v}`}>
              <line x1={PAD} y1={y} x2={x2} y2={y} stroke="#333" strokeWidth={0.5} />
              <text x={PAD - 4} y={y + 3} textAnchor="end" fill="#666" fontSize="7">{v.toFixed(2)}</text>
            </g>
          );
        })}
        {[0, 0.25, 0.5, 0.75, 1].map((v) => {
          const [x] = toSvg(v, 0);
          const [, y2] = toSvg(v, 1);
          return (
            <g key={`v${v}`}>
              <line x1={x} y1={PAD} x2={x} y2={H - PAD} stroke="#333" strokeWidth={0.5} />
              <text x={x} y={H - PAD + 12} textAnchor="middle" fill="#666" fontSize="7">{v.toFixed(2)}</text>
            </g>
          );
        })}

        {/* axes labels */}
        <text x={W / 2} y={H - 2} textAnchor="middle" fill="#888" fontSize="8">Recall</text>
        <text
          x={6} y={H / 2}
          textAnchor="middle" fill="#888" fontSize="8"
          transform={`rotate(-90,6,${H / 2})`}
        >
          Precision
        </text>

        {/* curves */}
        {entries.map(([name, pts]) => {
          const color = CLASS_COLORS[name] || "#888";
          const d = pts.map((p, i) => {
            const [x, y] = toSvg(p.r, p.p);
            return `${i === 0 ? "M" : "L"}${x},${y}`;
          }).join(" ");
          return <path key={name} d={d} fill="none" stroke={color} strokeWidth={1.5} opacity={0.9} />;
        })}

        {/* interactive hover line */}
        {hover != null && (() => {
          const [x] = toSvg(hover, 0);
          return <line x1={x} y1={PAD} x2={x} y2={H - PAD} stroke="#555" strokeWidth={0.5} strokeDasharray="2" />;
        })()}

        {/* invisible rect for mouse tracking */}
        <rect
          x={PAD} y={PAD}
          width={W - 2 * PAD} height={H - 2 * PAD}
          fill="transparent"
          onMouseMove={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const x = (e.clientX - rect.left) / rect.width;
            setHover(Math.max(0, Math.min(1, x)));
          }}
        />
      </svg>

      <div className="pr-legend">
        {entries.map(([name]) => (
          <span key={name} style={{ color: CLASS_COLORS[name] || "#888", fontSize: 11, marginRight: 10 }}>
            ● {name}
          </span>
        ))}
      </div>
    </div>
  );
}

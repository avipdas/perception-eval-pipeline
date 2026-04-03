import { useEffect, useState } from "react";
import { fetchFailures } from "../api";

const TABS = [
  { key: "worst_misses", label: "Worst Misses" },
  { key: "dangerous_errors", label: "Dangerous Errors" },
  { key: "hallucinations", label: "Hallucinations" },
];

export default function FailureBrowser({ onSelectFrame }) {
  const [tab, setTab] = useState("worst_misses");
  const [rows, setRows] = useState([]);

  useEffect(() => {
    fetchFailures(tab).then(setRows).catch(() => setRows([]));
  }, [tab]);

  return (
    <div className="panel failure-browser">
      <h3>Failure Cases</h3>
      <div className="tab-row">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`tab ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="failure-list">
        {rows.length === 0 && <div className="empty">No data</div>}
        {rows.map((row, i) => (
          <div
            key={i}
            className="failure-row"
            onClick={() => onSelectFrame(row.frame_id)}
          >
            <span className="failure-class">{row.class}</span>
            {row.distance_m != null && (
              <span>{row.distance_m}m</span>
            )}
            {row.lidar_pts != null && (
              <span>{row.lidar_pts} pts</span>
            )}
            {row.sde != null && (
              <span>SDE: {row.sde}</span>
            )}
            {row.confidence != null && (
              <span>Conf: {row.confidence}</span>
            )}
            <span className="failure-frame">Frame #{row.frame_id}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

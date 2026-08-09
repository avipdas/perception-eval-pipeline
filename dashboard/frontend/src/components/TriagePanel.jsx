import { useState } from "react";

const SEV_META = {
  critical:   { icon: "🔴", color: "#ef4444", label: "Critical" },
  high:       { icon: "🟠", color: "#f97316", label: "High"     },
  medium:     { icon: "🟡", color: "#eab308", label: "Medium"   },
  "low-medium":{ icon: "🟡", color: "#eab308", label: "Low-Med"  },
  low:        { icon: "🟢", color: "#22c55e", label: "Low"      },
  negligible: { icon: "⚪", color: "#64748b", label: "Negligible"},
};

const EVENT_COLORS = {
  FN: { bg: "#7f1d1d", fg: "#fca5a5", label: "MISSED" },
  FP: { bg: "#1e3a5f", fg: "#93c5fd", label: "PHANTOM" },
  TP: { bg: "#1a2e1a", fg: "#86efac", label: "DETECTED" },
};

function SeverityBadge({ sev }) {
  const m = SEV_META[sev] || SEV_META.low;
  return (
    <span style={{ color: m.color, fontWeight: 600, fontSize: "0.7rem" }}>
      {m.icon} {m.label}
    </span>
  );
}

function EventBadge({ type }) {
  const c = EVENT_COLORS[type] || { bg: "#333", fg: "#ccc", label: type };
  return (
    <span style={{
      background: c.bg, color: c.fg,
      fontSize: "0.62rem", fontWeight: 700,
      padding: "1px 5px", borderRadius: 3, letterSpacing: "0.06em",
    }}>
      {c.label}
    </span>
  );
}

function FindingRow({ finding, onHighlight }) {
  const [open, setOpen] = useState(false);
  const hasHighlight = !!finding.highlight_object_id;

  return (
    <div
      style={{
        borderLeft: `3px solid ${SEV_META[finding.safety_severity]?.color ?? "#555"}`,
        padding: "6px 8px",
        marginBottom: 4,
        background: "#1a2030",
        borderRadius: "0 4px 4px 0",
        cursor: "pointer",
      }}
      onClick={() => setOpen((v) => !v)}
    >
      {/* Row header */}
      <div style={{ display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap" }}>
        <EventBadge type={finding.event_type} />
        <span style={{ fontSize: "0.78rem", fontWeight: 600, color: "#e2e8f0" }}>
          {finding.object_class}
        </span>
        {finding.range_m != null && (
          <span style={{ fontSize: "0.72rem", color: "#94a3b8" }}>
            {finding.range_m.toFixed(1)} m
          </span>
        )}
        <SeverityBadge sev={finding.safety_severity} />
        <span style={{ marginLeft: "auto", fontSize: "0.65rem", color: "#475569" }}>
          {open ? "▲" : "▼"}
        </span>
      </div>

      {/* Failure code */}
      <div style={{ marginTop: 3, fontSize: "0.68rem", color: "#7dd3fc", fontFamily: "monospace" }}>
        {finding.failure_code || "—"}
      </div>

      {/* Expanded */}
      {open && (
        <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 5 }}>
          {finding.label && (
            <div style={{ fontSize: "0.72rem", color: "#cbd5e1", fontStyle: "italic" }}>
              {finding.label}
            </div>
          )}
          <div style={{
            fontSize: "0.72rem", color: "#94a3b8", lineHeight: 1.45,
            background: "#111827", padding: "5px 7px", borderRadius: 3,
          }}>
            {finding.rationale}
          </div>
          {finding.recommended_action && (
            <div style={{
              fontSize: "0.7rem", color: "#6ee7b7", lineHeight: 1.4,
              borderTop: "1px solid #1e293b", paddingTop: 4,
            }}>
              <strong style={{ color: "#34d399" }}>Action: </strong>
              {finding.recommended_action}
            </div>
          )}
          {hasHighlight && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onHighlight(finding.highlight_object_id); }}
              style={{
                alignSelf: "flex-start",
                background: "#1e40af", color: "#bfdbfe",
                border: "1px solid #3b82f6", borderRadius: 4,
                fontSize: "0.68rem", padding: "3px 8px", cursor: "pointer",
                marginTop: 2,
              }}
            >
              Highlight in 3D ↗
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default function TriagePanel({ triageResult, loading, onHighlight }) {
  const [filterSev, setFilterSev] = useState(null);

  if (loading) {
    return (
      <div className="panel">
        <h3>LLM Triage</h3>
        <div style={{ color: "#64748b", fontSize: "0.8rem", padding: "8px 0" }}>
          Fetching triage…
        </div>
      </div>
    );
  }

  if (!triageResult || triageResult.error === "no_triage_data") {
    return (
      <div className="panel">
        <h3>LLM Triage</h3>
        <div style={{ color: "#64748b", fontSize: "0.78rem", lineHeight: 1.5 }}>
          No triage data for this frame.
          <br />
          Run: <code style={{ fontSize: "0.7rem", color: "#94a3b8" }}>
            python -m scripts.run_triage
          </code>
        </div>
      </div>
    );
  }

  const findings = triageResult.findings ?? [];

  // Severity counts for header badges
  const counts = findings.reduce((acc, f) => {
    const s = f.safety_severity || "low";
    acc[s] = (acc[s] || 0) + 1;
    return acc;
  }, {});

  const sorted = [...findings].sort((a, b) => {
    const order = ["critical", "high", "medium", "low-medium", "low", "negligible"];
    return order.indexOf(a.safety_severity) - order.indexOf(b.safety_severity);
  });

  const visible = filterSev ? sorted.filter((f) => f.safety_severity === filterSev) : sorted;

  return (
    <div className="panel">
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>LLM Triage</h3>
        <div style={{ display: "flex", gap: 4 }}>
          {counts.critical > 0 && (
            <span style={{ background: "#7f1d1d", color: "#fca5a5", fontSize: "0.65rem", fontWeight: 700, padding: "2px 6px", borderRadius: 10 }}>
              🔴 {counts.critical}
            </span>
          )}
          {counts.high > 0 && (
            <span style={{ background: "#431407", color: "#fed7aa", fontSize: "0.65rem", fontWeight: 700, padding: "2px 6px", borderRadius: 10 }}>
              🟠 {counts.high}
            </span>
          )}
        </div>
      </div>

      {/* Frame summary */}
      {triageResult.frame_summary && (
        <div style={{
          fontSize: "0.75rem", color: "#94a3b8", lineHeight: 1.5,
          background: "#0f172a", border: "1px solid #1e293b",
          borderRadius: 4, padding: "7px 9px", marginBottom: 10,
        }}>
          {triageResult.frame_summary}
        </div>
      )}

      {/* Severity filter pills */}
      {findings.length > 0 && (
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 8 }}>
          <button
            type="button"
            onClick={() => setFilterSev(null)}
            style={{
              background: filterSev === null ? "#334155" : "transparent",
              border: "1px solid #334155", borderRadius: 10,
              color: "#94a3b8", fontSize: "0.65rem", padding: "2px 7px", cursor: "pointer",
            }}
          >
            All ({findings.length})
          </button>
          {["critical", "high", "medium", "low"].map((sev) => counts[sev] ? (
            <button
              key={sev}
              type="button"
              onClick={() => setFilterSev(filterSev === sev ? null : sev)}
              style={{
                background: filterSev === sev ? SEV_META[sev].color + "33" : "transparent",
                border: `1px solid ${SEV_META[sev].color}66`,
                borderRadius: 10, color: SEV_META[sev].color,
                fontSize: "0.65rem", padding: "2px 7px", cursor: "pointer",
              }}
            >
              {SEV_META[sev].icon} {counts[sev]}
            </button>
          ) : null)}
        </div>
      )}

      {/* Findings list */}
      <div style={{ maxHeight: 420, overflowY: "auto", paddingRight: 2 }}>
        {visible.length === 0 && (
          <div style={{ color: "#475569", fontSize: "0.78rem" }}>No findings match filter.</div>
        )}
        {visible.map((f, i) => (
          <FindingRow key={i} finding={f} onHighlight={onHighlight} />
        ))}
      </div>

      {/* Footer */}
      <div style={{ marginTop: 6, fontSize: "0.65rem", color: "#334155" }}>
        Model: {triageResult.model || "—"} · {triageResult.latency_s?.toFixed(1)}s
      </div>
    </div>
  );
}

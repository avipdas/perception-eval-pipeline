function formatTs(micros) {
  if (micros == null) return "—";
  const ms = Math.floor(micros / 1000);
  try {
    return new Date(ms).toISOString().replace("T", " ").slice(0, 19) + "Z";
  } catch {
    return String(micros);
  }
}

export default function RunMetadataStrip({
  runName,
  frame,
  loading,
  sessionStartedAt,
}) {
  return (
    <div className="metadata-strip tabular-nums" aria-label="Run metadata">
      <div className="metadata-strip-inner">
        <span className="metadata-kv">
          <span className="metadata-key">Run</span>
          <span className="metadata-val">{runName}</span>
        </span>
        <span className="metadata-sep" />
        <span className="metadata-kv">
          <span className="metadata-key">Model</span>
          <span className="metadata-val">Synthetic baseline</span>
        </span>
        <span className="metadata-sep" />
        <span className="metadata-kv">
          <span className="metadata-key">Segment</span>
          <span className="metadata-val" title={frame?.context_name}>
            {frame?.context_name ? frame.context_name.slice(0, 28) + (frame.context_name.length > 28 ? "…" : "") : "—"}
          </span>
        </span>
        <span className="metadata-sep" />
        <span className="metadata-kv">
          <span className="metadata-key">Frame</span>
          <span className="metadata-val">
            {frame ? `#${frame.id} · idx ${frame.frame_index}` : "—"}
          </span>
        </span>
        <span className="metadata-sep" />
        <span className="metadata-kv">
          <span className="metadata-key">Timestamp</span>
          <span className="metadata-val">{formatTs(frame?.timestamp_micros)}</span>
        </span>
        <span className="metadata-sep" />
        <span className="metadata-kv">
          <span className="metadata-key">Session</span>
          <span className="metadata-val">{sessionStartedAt}</span>
        </span>
        {loading && <span className="metadata-loading">Updating…</span>}
      </div>
    </div>
  );
}

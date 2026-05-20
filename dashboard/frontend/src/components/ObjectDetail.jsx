const TYPE_NAMES = { 1: "VEHICLE", 2: "PEDESTRIAN", 4: "CYCLIST" };

function matchColor(matchType) {
  if (matchType === "TP") return "#1ce8b5";
  if (matchType === "FP") return "#ea4335";
  if (matchType === "FN") return "#fbbc04";
  return "#9aa0a6";
}

export default function ObjectDetail({ box, onClose }) {
  if (!box) return null;

  const type = TYPE_NAMES[box.object_type] || "UNKNOWN";
  const isDangerous = box.signed_sde != null && box.signed_sde > 0;
  const mColor = matchColor(box.match_type);

  return (
    <div className="object-detail">
      <div className="object-detail-header">
        <h4 style={{ color: mColor }}>{type}</h4>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            className="detail-badge"
            style={{ background: `${mColor}18`, color: mColor, border: `1px solid ${mColor}40` }}
          >
            {box.source.toUpperCase()} · {box.match_type || "—"}
          </span>
          <button className="object-detail-close" onClick={onClose}>✕</button>
        </div>
      </div>

      <div className="detail-grid">
        {box.iou != null && (
          <div className="detail-cell">
            <span className="detail-cell-value">{box.iou.toFixed(3)}</span>
            <span className="detail-cell-label">IoU</span>
          </div>
        )}
        {box.confidence != null && (
          <div className="detail-cell">
            <span className="detail-cell-value">{box.confidence.toFixed(3)}</span>
            <span className="detail-cell-label">Confidence</span>
          </div>
        )}
        {box.heading_accuracy != null && (
          <div className="detail-cell">
            <span className="detail-cell-value" style={{
              color: box.heading_accuracy > 0.9 ? "#1ce8b5" : box.heading_accuracy > 0.7 ? "#fbbc04" : "#ea4335"
            }}>
              {box.heading_accuracy.toFixed(3)}
            </span>
            <span className="detail-cell-label">Heading Acc</span>
          </div>
        )}
        {box.range != null && (
          <div className="detail-cell">
            <span className="detail-cell-value">{box.range.toFixed(1)}m</span>
            <span className="detail-cell-label">Range</span>
          </div>
        )}
      </div>

      {box.sde != null && (
        <div
          className="detail-sde-row"
          style={{
            background: isDangerous ? "rgba(234,67,53,0.1)" : "rgba(28,232,181,0.06)",
            border: `1px solid ${isDangerous ? "rgba(234,67,53,0.3)" : "rgba(28,232,181,0.2)"}`,
          }}
        >
          <div>
            <div style={{ fontSize: 10, color: "#9aa0a6", textTransform: "uppercase" }}>
              Support Distance Error
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, color: isDangerous ? "#ea4335" : "#1ce8b5" }}>
              {box.sde.toFixed(3)}m
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 10, color: "#6b7280" }}>Signed</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: isDangerous ? "#ea4335" : "#1ce8b5" }}>
              {box.signed_sde != null ? `${box.signed_sde.toFixed(3)}m` : "—"}
            </div>
            {box.signed_sde != null && (
              <div style={{ fontSize: 9, color: "#6b7280" }}>
                {isDangerous ? "closer than GT" : "farther / conservative vs GT"}
              </div>
            )}
          </div>
        </div>
      )}

      <div className="detail-dims">
        Dimensions: {box.length.toFixed(1)} × {box.width.toFixed(1)} × {box.height.toFixed(1)} m
        &nbsp;|&nbsp; Heading: {((box.heading * 180) / Math.PI).toFixed(1)}°
        &nbsp;|&nbsp; ID: {box.object_id}
      </div>
    </div>
  );
}

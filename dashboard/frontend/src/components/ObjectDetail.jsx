const TYPE_NAMES = { 1: "VEHICLE", 2: "PEDESTRIAN", 4: "CYCLIST" };

function matchColor(matchType) {
  if (matchType === "TP") return "#00e5ff";
  if (matchType === "FP") return "#ff5252";
  if (matchType === "FN") return "#ffc107";
  return "#546e7a";
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
              color: box.heading_accuracy > 0.9 ? "#69f0ae" : box.heading_accuracy > 0.7 ? "#ffc107" : "#ff5252"
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
            background: isDangerous ? "rgba(255,82,82,0.1)" : "rgba(105,240,174,0.06)",
            border: `1px solid ${isDangerous ? "rgba(255,82,82,0.3)" : "rgba(105,240,174,0.2)"}`,
          }}
        >
          <div>
            <div style={{ fontSize: 10, color: "#7986cb", textTransform: "uppercase" }}>
              Support Distance Error
            </div>
            <div style={{ fontSize: 18, fontWeight: 700, color: isDangerous ? "#ff5252" : "#69f0ae" }}>
              {box.sde.toFixed(3)}m
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 10, color: "#5c6bc0" }}>Signed</div>
            <div style={{ fontSize: 13, fontWeight: 600, color: isDangerous ? "#ff5252" : "#69f0ae" }}>
              {box.signed_sde != null ? `${box.signed_sde.toFixed(3)}m` : "—"}
            </div>
            {box.signed_sde != null && (
              <div style={{ fontSize: 9, color: "#5c6bc0" }}>
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

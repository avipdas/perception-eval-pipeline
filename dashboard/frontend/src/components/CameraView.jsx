import { useState } from "react";
import { cameraUrl } from "../api";

export default function CameraView({ frameId }) {
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState(false);

  if (frameId == null) return null;

  const url = cameraUrl(frameId);

  if (error) return null;

  return (
    <div
      className={`camera-view ${expanded ? "expanded" : ""}`}
      onClick={() => setExpanded(!expanded)}
    >
      <img
        src={url}
        alt="Front camera"
        onError={() => setError(true)}
        key={frameId}
      />
      <div className="camera-label">Front Camera</div>
    </div>
  );
}

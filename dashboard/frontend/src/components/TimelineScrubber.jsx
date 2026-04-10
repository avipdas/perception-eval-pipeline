import { useRef, useCallback, useMemo } from "react";

function lerpColor(a, b, t) {
  const ar = parseInt(a.slice(1, 3), 16), ag = parseInt(a.slice(3, 5), 16), ab = parseInt(a.slice(5, 7), 16);
  const br = parseInt(b.slice(1, 3), 16), bg = parseInt(b.slice(3, 5), 16), bb = parseInt(b.slice(5, 7), 16);
  const r = Math.round(ar + (br - ar) * t), g = Math.round(ag + (bg - ag) * t), bl = Math.round(ab + (bb - ab) * t);
  return `#${r.toString(16).padStart(2,"0")}${g.toString(16).padStart(2,"0")}${bl.toString(16).padStart(2,"0")}`;
}

export default function TimelineScrubber({ frames, currentId, onChange, frameStats }) {
  const trackRef = useRef(null);

  const idx = frames.findIndex((f) => f.id === currentId);

  const handleClick = useCallback(
    (e) => {
      if (!trackRef.current || frames.length === 0) return;
      const rect = trackRef.current.getBoundingClientRect();
      const frac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const i = Math.round(frac * (frames.length - 1));
      onChange(frames[i].id);
    },
    [frames, onChange]
  );

  const handleDrag = useCallback(
    (e) => {
      if (e.buttons !== 1) return;
      handleClick(e);
    },
    [handleClick]
  );

  const qualityMap = useMemo(() => {
    if (!frames?.length || !frameStats) return {};
    const scores = [];
    const totals = [];
    for (const f of frames) {
      const s = frameStats[f.id];
      if (!s) continue;
      const total = s.tp + s.fp + s.fn;
      if (total === 0) continue;
      const score = (2 * s.tp) / (2 * s.tp + s.fp + s.fn);
      scores.push(score);
      totals.push(total);
    }
    if (scores.length === 0) return {};
    const minS = Math.min(...scores);
    const maxS = Math.max(...scores);
    const range = maxS - minS || 1;
    const maxTotal = Math.max(...totals);

    const RED = "#ff5252";
    const YELLOW = "#ffc107";
    const GREEN = "#69f0ae";

    const map = {};
    for (const f of frames) {
      const s = frameStats[f.id];
      if (!s) continue;
      const total = s.tp + s.fp + s.fn;
      if (total === 0) continue;
      const score = (2 * s.tp) / (2 * s.tp + s.fp + s.fn);
      const t = (score - minS) / range;
      const color = t < 0.5 ? lerpColor(RED, YELLOW, t * 2) : lerpColor(YELLOW, GREEN, (t - 0.5) * 2);
      const heightPct = Math.max(30, (total / maxTotal) * 100);
      map[f.id] = { color, heightPct };
    }
    return map;
  }, [frames, frameStats]);

  if (!frames || frames.length === 0) return null;

  const thumbLeft = frames.length > 1 ? `${(idx / (frames.length - 1)) * 100}%` : "0%";

  return (
    <div className="timeline-container">
      <div
        ref={trackRef}
        className="timeline-track"
        onClick={handleClick}
        onMouseMove={handleDrag}
      >
        <div className="timeline-ticks">
          {frames.map((f, i) => {
            const q = qualityMap[f.id];
            const isCurrent = i === idx;
            let bg = "#2a3070";
            let h = "40%";
            let op = 0.5;
            if (q != null) {
              bg = q.color;
              h = `${Math.max(30, Math.min(100, q.heightPct))}%`;
              op = 0.85;
            }
            return (
              <div
                key={f.id}
                className="timeline-tick"
                style={{
                  background: isCurrent ? "#00e5ff" : bg,
                  height: isCurrent ? "100%" : h,
                  opacity: isCurrent ? 1 : op,
                  borderRadius: 2,
                }}
              />
            );
          })}
        </div>
        <div className="timeline-thumb" style={{ left: thumbLeft }} />
      </div>
      <div className="timeline-labels">
        <span>Frame 1</span>
        <span>{idx + 1} / {frames.length}</span>
        <span>Frame {frames.length}</span>
      </div>
    </div>
  );
}

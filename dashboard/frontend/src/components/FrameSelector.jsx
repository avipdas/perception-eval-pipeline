import { useEffect, useRef, useState } from "react";

const SPEED_OPTIONS = [
  { label: "0.5×", ms: 2000 },
  { label: "1×", ms: 1000 },
  { label: "2×", ms: 500 },
  { label: "4×", ms: 250 },
];

export default function FrameSelector({ frames, currentId, onChange, loading }) {
  const [playing, setPlaying] = useState(false);
  const [speedIdx, setSpeedIdx] = useState(1);
  const timerRef = useRef(null);

  const idx = frames.findIndex((f) => f.id === currentId);
  const current = frames[idx] ?? null;

  useEffect(() => {
    if (!playing) {
      clearInterval(timerRef.current);
      return;
    }
    timerRef.current = setInterval(() => {
      onChange((prevId) => {
        const i = frames.findIndex((f) => f.id === prevId);
        if (i >= frames.length - 1) {
          setPlaying(false);
          return prevId;
        }
        return frames[i + 1].id;
      });
    }, SPEED_OPTIONS[speedIdx].ms);
    return () => clearInterval(timerRef.current);
  }, [playing, speedIdx, frames, onChange]);

  if (!frames || frames.length === 0) return <div className="panel">Loading frames...</div>;

  return (
    <div className="panel">
      <h3>Frame</h3>
      <div className="frame-nav">
        <button
          className="play-btn"
          onClick={() => setPlaying(!playing)}
          title={playing ? "Pause" : "Play"}
        >
          {playing ? "⏸" : "▶"}
        </button>
        <button disabled={idx <= 0 || loading} onClick={() => onChange(frames[idx - 1].id)}>
          ◀
        </button>
        <select value={currentId ?? ""} onChange={(e) => onChange(Number(e.target.value))}>
          {frames.map((f) => (
            <option key={f.id} value={f.id}>
              #{f.id} — idx {f.frame_index}
            </option>
          ))}
        </select>
        <button
          disabled={idx >= frames.length - 1 || loading}
          onClick={() => onChange(frames[idx + 1].id)}
        >
          ▶
        </button>
      </div>

      <div className="playback-controls">
        <span className="speed-label">Speed:</span>
        {SPEED_OPTIONS.map((s, i) => (
          <button
            key={s.label}
            className={`speed-btn ${i === speedIdx ? "active" : ""}`}
            onClick={() => setSpeedIdx(i)}
          >
            {s.label}
          </button>
        ))}
        <span className="frame-counter">{idx + 1} / {frames.length}</span>
      </div>

      {current && (
        <div className="frame-meta">
          <span>{current.location}</span>
          <span>{current.weather}</span>
          <span>{current.time_of_day}</span>
        </div>
      )}
    </div>
  );
}

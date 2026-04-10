import { useMemo, useState, useRef } from "react";
import * as THREE from "three";
import { Html, Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";

const TYPE_NAMES = { 1: "VEHICLE", 2: "PEDESTRIAN", 4: "CYCLIST" };

const BOX_COLORS = {
  gt_tp: "#00e5ff",
  gt_fn: "#ffc107",
  gt_none: "#546e7a",
  pred_tp: "#b388ff",
  pred_fp: "#ff5252",
  pred_none: "#546e7a",
};

function boxColor(box) {
  if (box.source === "gt") {
    if (box.match_type === "TP") return BOX_COLORS.gt_tp;
    if (box.match_type === "FN") return BOX_COLORS.gt_fn;
    return BOX_COLORS.gt_none;
  }
  if (box.match_type === "TP") return BOX_COLORS.pred_tp;
  if (box.match_type === "FP") return BOX_COLORS.pred_fp;
  return BOX_COLORS.pred_none;
}

function isInCorridor(box) {
  return box.center_x > 0 && box.center_x < 50 && Math.abs(box.center_y) < 1.5;
}

/* ── Heading Arrow ─────────────────────────────────────────── */
function HeadingArrow({ box }) {
  const { points, color } = useMemo(() => {
    const len = Math.min(box.length * 0.6, 3);
    const acc = box.heading_accuracy;
    let c = "#69f0ae";
    if (acc != null) {
      if (acc < 0.7) c = "#ff5252";
      else if (acc < 0.9) c = "#ffc107";
    }
    const cos = Math.cos(box.heading);
    const sin = Math.sin(box.heading);
    const cx = box.center_x;
    const cy = box.center_y;
    const cz = box.center_z;
    const tipX = cx + cos * len;
    const tipY = cy + sin * len;
    const leftX = cx + cos * len * 0.6 - sin * 0.3;
    const leftY = cy + sin * len * 0.6 + cos * 0.3;
    const rightX = cx + cos * len * 0.6 + sin * 0.3;
    const rightY = cy + sin * len * 0.6 - cos * 0.3;
    return {
      points: [
        [cx, cy, cz], [tipX, tipY, cz],
        [tipX, tipY, cz], [leftX, leftY, cz],
        [tipX, tipY, cz], [rightX, rightY, cz],
      ],
      color: c,
    };
  }, [box]);

  const linePoints = [];
  for (let i = 0; i < points.length; i += 2) {
    linePoints.push(points[i], points[i + 1]);
  }

  return (
    <group>
      <Line points={[points[0], points[1]]} color={color} lineWidth={2} />
      <Line points={[points[2], points[3]]} color={color} lineWidth={2} />
      <Line points={[points[4], points[5]]} color={color} lineWidth={2} />
    </group>
  );
}

/* ── Motion Vector (GT→Pred offset for TPs) ───────────────── */
function MotionVectors({ boxes }) {
  const pairs = useMemo(() => {
    if (!boxes) return [];
    const gtMap = {};
    const predMap = {};
    boxes.forEach((b) => {
      if (b.match_type === "TP") {
        if (b.source === "gt") gtMap[b.object_id] = b;
        else predMap[b.object_id] = b;
      }
    });
    const result = [];
    Object.keys(gtMap).forEach((id) => {
      if (predMap[id]) {
        const g = gtMap[id];
        const p = predMap[id];
        result.push({
          from: [g.center_x, g.center_y, g.center_z],
          to: [p.center_x, p.center_y, p.center_z],
        });
      }
    });
    return result;
  }, [boxes]);

  if (pairs.length === 0) return null;

  return (
    <group>
      {pairs.map((pair, i) => (
        <Line
          key={i}
          points={[pair.from, pair.to]}
          color="#e040fb"
          lineWidth={2}
          dashed
          dashSize={0.3}
          gapSize={0.15}
        />
      ))}
    </group>
  );
}

/* ── Corridor Pulse Glow ───────────────────────────────────── */
function CorridorGlow({ box }) {
  const meshRef = useRef();
  useFrame(({ clock }) => {
    if (meshRef.current) {
      meshRef.current.material.opacity = 0.15 + Math.sin(clock.elapsedTime * 4) * 0.1;
    }
  });

  const matrix = useMemo(() => {
    const m = new THREE.Matrix4();
    m.makeRotationZ(box.heading);
    m.setPosition(box.center_x, box.center_y, box.center_z);
    return m;
  }, [box]);

  return (
    <group matrixAutoUpdate={false} matrix={matrix}>
      <mesh ref={meshRef}>
        <boxGeometry args={[box.length + 0.4, box.width + 0.4, box.height + 0.4]} />
        <meshBasicMaterial color="#ff5252" transparent opacity={0.2} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

/* ── Failure list focus: vertical stem + arrow toward box top (z-up) ─ */
function FailureHighlightPointer({ boxes, highlightId }) {
  const groupRef = useRef();
  const spec = useMemo(() => {
    if (!highlightId || !boxes?.length) return null;
    const b = boxes.find((x) => x.object_id === highlightId);
    if (!b) return null;
    const cx = b.center_x;
    const cy = b.center_y;
    const topZ = b.center_z + b.height / 2;
    const stemTop = topZ + Math.min(6, Math.max(3.5, b.length * 0.55));
    const joinZ = topZ + 0.85;
    const tipZ = topZ + 0.12;
    const wing = Math.min(0.55, b.length * 0.22);
    return { cx, cy, stemTop, joinZ, tipZ, wing };
  }, [boxes, highlightId]);

  useFrame(({ clock }) => {
    if (!groupRef.current || !spec) return;
    const w = 0.06 * Math.sin(clock.elapsedTime * 2.8);
    groupRef.current.position.set(0, 0, w);
  });

  if (!spec) return null;
  const { cx, cy, stemTop, joinZ, tipZ, wing } = spec;
  const col = "#ffea00";

  return (
    <group ref={groupRef}>
      <Line points={[[cx, cy, stemTop], [cx, cy, joinZ]]} color={col} lineWidth={3} />
      <Line points={[[cx - wing, cy, joinZ], [cx, cy, tipZ]]} color={col} lineWidth={3} />
      <Line points={[[cx + wing, cy, joinZ], [cx, cy, tipZ]]} color={col} lineWidth={3} />
      <mesh position={[cx, cy, stemTop + 0.12]}>
        <sphereGeometry args={[0.22, 12, 12]} />
        <meshBasicMaterial color={col} depthTest={false} />
      </mesh>
    </group>
  );
}

/* ── Wireframe Box ─────────────────────────────────────────── */
function WireframeBox({ box, onHover, onUnhover, selected, onClick }) {
  const { geometry, matrix } = useMemo(() => {
    const geo = new THREE.EdgesGeometry(
      new THREE.BoxGeometry(box.length, box.width, box.height)
    );
    const mat = new THREE.Matrix4();
    mat.makeRotationZ(box.heading);
    mat.setPosition(box.center_x, box.center_y, box.center_z);
    return { geometry: geo, matrix: mat };
  }, [box]);

  const color = boxColor(box);
  const lineWidth = selected ? 3 : 1.5;

  return (
    <group matrixAutoUpdate={false} matrix={matrix}>
      <lineSegments
        geometry={geometry}
        onPointerOver={(e) => { e.stopPropagation(); onHover(box); }}
        onPointerOut={() => onUnhover()}
        onClick={(e) => { e.stopPropagation(); onClick?.(box); }}
      >
        <lineBasicMaterial color={color} linewidth={lineWidth} />
      </lineSegments>
    </group>
  );
}

/* ── Tooltip ───────────────────────────────────────────────── */
function Tooltip({ box }) {
  if (!box) return null;
  const type = TYPE_NAMES[box.object_type] || "UNKNOWN";
  const isDangerous = box.signed_sde != null && box.signed_sde > 0;
  return (
    <Html
      position={[box.center_x, box.center_y, box.center_z + box.height / 2 + 0.5]}
      center
      style={{ pointerEvents: "none" }}
    >
      <div
        style={{
          background: "rgba(10,14,39,0.92)",
          color: "#e8eaf6",
          padding: "8px 12px",
          borderRadius: 8,
          fontSize: 11,
          whiteSpace: "nowrap",
          fontFamily: "'Roboto Mono', monospace",
          border: `1px solid ${boxColor(box)}`,
          boxShadow: "0 4px 20px rgba(0,0,0,0.6)",
          minWidth: 160,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <strong style={{ fontSize: 12, color: "#e8eaf6" }}>{type}</strong>
          <span style={{ fontSize: 10, color: "#7986cb" }}>
            {box.source.toUpperCase()} {box.match_type && `· ${box.match_type}`}
          </span>
        </div>
        {box.sde != null && (
          <div style={{
            background: isDangerous ? "rgba(255,82,82,0.12)" : "rgba(105,240,174,0.08)",
            border: `1px solid ${isDangerous ? "#ff5252" : "#69f0ae"}`,
            borderRadius: 4,
            padding: "4px 8px",
            marginBottom: 4,
            display: "flex",
            justifyContent: "space-between",
          }}>
            <span style={{ color: "#9fa8da" }}>SDE</span>
            <span style={{ fontWeight: 700, color: isDangerous ? "#ff5252" : "#69f0ae" }}>
              {box.sde.toFixed(3)}m {isDangerous ? "DANGER" : "safe"}
            </span>
          </div>
        )}
        {box.signed_sde != null && (
          <div style={{ fontSize: 10, color: "#5c6bc0", marginBottom: 2 }}>
            Signed: {box.signed_sde.toFixed(3)}m
            {box.signed_sde > 0 ? " (closer)" : " (farther)"}
          </div>
        )}
        <div style={{ display: "flex", gap: 12, marginTop: 4, color: "#c5cae9" }}>
          {box.iou != null && <span>IoU: <strong>{box.iou.toFixed(3)}</strong></span>}
          {box.confidence != null && <span>Conf: <strong>{box.confidence.toFixed(3)}</strong></span>}
        </div>
        {box.heading_accuracy != null && (
          <div style={{ fontSize: 10, color: "#5c6bc0", marginTop: 2 }}>
            Heading: {box.heading_accuracy.toFixed(3)}
          </div>
        )}
        {box.range != null && (
          <div style={{ fontSize: 10, color: "#5c6bc0" }}>
            Range: {box.range.toFixed(1)}m
          </div>
        )}
      </div>
    </Html>
  );
}

/* ── Main Component ────────────────────────────────────────── */
export default function BoundingBoxes({
  boxes,
  showGt = true,
  showPred = true,
  filterTypes = null,
  filterMatch = null,
  highlightId = null,
  showCorridor = false,
  showMotionVectors = true,
  onSelectBox,
  selectedBoxId,
}) {
  const [hovered, setHovered] = useState(null);

  const filtered = useMemo(() => {
    if (!boxes) return [];
    return boxes.filter((b) => {
      if (b.source === "gt" && !showGt) return false;
      if (b.source === "pred" && !showPred) return false;
      if (filterTypes && !filterTypes.includes(b.object_type)) return false;
      if (filterMatch && b.match_type && !filterMatch.includes(b.match_type)) return false;
      return true;
    });
  }, [boxes, showGt, showPred, filterTypes, filterMatch]);

  const corridorIntruders = useMemo(() => {
    if (!showCorridor || !filtered) return [];
    return filtered.filter(isInCorridor);
  }, [filtered, showCorridor]);

  return (
    <group>
      {filtered.map((box, i) => (
        <group key={`${box.source}-${box.object_id}-${i}`}>
          <WireframeBox
            box={box}
            onHover={setHovered}
            onUnhover={() => setHovered(null)}
            selected={selectedBoxId === box.object_id}
            onClick={onSelectBox}
          />
          <HeadingArrow box={box} />
        </group>
      ))}

      {showMotionVectors && <MotionVectors boxes={boxes} />}

      {corridorIntruders.map((box, i) => (
        <CorridorGlow key={`glow-${box.object_id}-${i}`} box={box} />
      ))}

      <FailureHighlightPointer boxes={boxes} highlightId={highlightId} />

      <Tooltip box={hovered} />
    </group>
  );
}

export { BOX_COLORS };

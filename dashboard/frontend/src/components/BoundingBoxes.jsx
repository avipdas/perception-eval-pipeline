import { useMemo, useState, useRef } from "react";
import * as THREE from "three";
import { Html, Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";

const TYPE_NAMES = { 1: "VEHICLE", 2: "PEDESTRIAN", 4: "CYCLIST" };

const BOX_COLORS = {
  gt_tp: "#1a73e8",
  gt_fn: "#fbbc04",
  gt_none: "#9aa0a6",
  pred_tp: "#1ce8b5",
  pred_fp: "#ea4335",
  pred_none: "#9aa0a6",
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
    let c = "#1ce8b5";
    if (acc != null) {
      if (acc < 0.7) c = "#ea4335";
      else if (acc < 0.9) c = "#fbbc04";
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
function MotionVectorArrow({ pair }) {
  const [hovered, setHovered] = useState(false);

  const markerPos = useMemo(() => {
    const topZ = Math.max(
      pair.gt.center_z + pair.gt.height / 2,
      pair.pred.center_z + pair.pred.height / 2,
    );
    return [
      (pair.from[0] + pair.to[0]) / 2,
      (pair.from[1] + pair.to[1]) / 2,
      topZ + 0.6,
    ];
  }, [pair]);

  const tooltipPos = useMemo(() => [
    markerPos[0], markerPos[1], markerPos[2] + 1.2,
  ], [markerPos]);

  const gt = pair.gt;
  const pred = pair.pred;
  const speed = Math.sqrt((gt.speed_x ?? 0) ** 2 + (gt.speed_y ?? 0) ** 2);
  const headingDeg = ((gt.heading * 180) / Math.PI).toFixed(1);
  const offsetDist = Math.sqrt(
    (pred.center_x - gt.center_x) ** 2 +
    (pred.center_y - gt.center_y) ** 2 +
    (pred.center_z - gt.center_z) ** 2,
  ).toFixed(3);

  return (
    <group>
      <Line
        points={[pair.from, pair.to]}
        color={hovered ? "#1ce8b5" : "#1a73e8"}
        lineWidth={hovered ? 3 : 2}
        dashed
        dashSize={0.3}
        gapSize={0.15}
        raycast={() => null}
      />
      {/* Hoverable diamond marker above the midpoint */}
      <mesh
        position={markerPos}
        rotation={[0, 0, Math.PI / 4]}
        onPointerOver={(e) => { e.stopPropagation(); setHovered(true); }}
        onPointerOut={() => setHovered(false)}
      >
        <boxGeometry args={[0.5, 0.5, 0.5]} />
        <meshBasicMaterial
          color={hovered ? "#1ce8b5" : "#1a73e8"}
          transparent
          opacity={hovered ? 0.9 : 0.55}
          depthTest={false}
        />
      </mesh>
      {hovered && (
        <Html position={tooltipPos} center style={{ pointerEvents: "none" }}>
          <div style={{
            background: "rgba(13,17,23,0.94)",
            color: "#ffffff",
            padding: "8px 12px",
            borderRadius: 8,
            fontSize: 11,
            whiteSpace: "nowrap",
            fontFamily: "'Roboto Mono', monospace",
            border: "1px solid #1a73e8",
            boxShadow: "0 4px 20px rgba(0,0,0,0.6)",
            minWidth: 180,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <strong style={{ color: "#1a73e8" }}>{TYPE_NAMES[gt.object_type] || "?"}</strong>
              <span style={{ fontSize: 10, color: "#9aa0a6" }}>GT → Pred offset</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "3px 12px", fontSize: 10 }}>
              <span style={{ color: "#9aa0a6" }}>Speed</span>
              <span style={{ fontWeight: 600 }}>{speed.toFixed(1)} m/s</span>
              <span style={{ color: "#9aa0a6" }}>Velocity</span>
              <span style={{ fontWeight: 600 }}>({(gt.speed_x ?? 0).toFixed(1)}, {(gt.speed_y ?? 0).toFixed(1)})</span>
              <span style={{ color: "#9aa0a6" }}>Heading</span>
              <span style={{ fontWeight: 600 }}>{headingDeg}°</span>
              <span style={{ color: "#9aa0a6" }}>Range</span>
              <span style={{ fontWeight: 600 }}>{gt.range?.toFixed(1)}m</span>
              <span style={{ color: "#9aa0a6" }}>LiDAR pts</span>
              <span style={{ fontWeight: 600 }}>{gt.num_lidar_points ?? "—"}</span>
              <span style={{ color: "#9aa0a6" }}>Offset</span>
              <span style={{ fontWeight: 600, color: "#1ce8b5" }}>{offsetDist}m</span>
              {gt.iou != null && <>
                <span style={{ color: "#9aa0a6" }}>IoU</span>
                <span style={{ fontWeight: 600 }}>{gt.iou.toFixed(3)}</span>
              </>}
              {gt.heading_accuracy != null && <>
                <span style={{ color: "#9aa0a6" }}>Head. Acc</span>
                <span style={{ fontWeight: 600 }}>{gt.heading_accuracy.toFixed(3)}</span>
              </>}
              {gt.detection_difficulty != null && <>
                <span style={{ color: "#9aa0a6" }}>Difficulty</span>
                <span style={{ fontWeight: 600 }}>{gt.detection_difficulty === 0 ? "Easy" : "Hard"}</span>
              </>}
            </div>
          </div>
        </Html>
      )}
    </group>
  );
}

function MotionVectors({ boxes }) {
  const pairs = useMemo(() => {
    if (!boxes) return [];
    const byId = {};
    boxes.forEach((b) => { byId[b.object_id] = b; });

    const result = [];
    boxes.forEach((b) => {
      if (b.source === "gt" && b.match_type === "TP" && b.matched_object_id) {
        const pred = byId[b.matched_object_id];
        if (pred) {
          result.push({
            from: [b.center_x, b.center_y, b.center_z],
            to: [pred.center_x, pred.center_y, pred.center_z],
            gt: b,
            pred,
          });
        }
      }
    });
    return result;
  }, [boxes]);

  if (pairs.length === 0) return null;

  return (
    <group>
      {pairs.map((pair, i) => (
        <MotionVectorArrow key={i} pair={pair} />
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
        <meshBasicMaterial color="#ea4335" transparent opacity={0.2} side={THREE.DoubleSide} />
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
  const col = "#fbbc04";

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
  const { edgesGeo, fillGeo, matrix } = useMemo(() => {
    const boxGeo = new THREE.BoxGeometry(box.length, box.width, box.height);
    const edges = new THREE.EdgesGeometry(boxGeo);
    const mat = new THREE.Matrix4();
    mat.makeRotationZ(box.heading);
    mat.setPosition(box.center_x, box.center_y, box.center_z);
    return { edgesGeo: edges, fillGeo: boxGeo, matrix: mat };
  }, [box]);

  const color = boxColor(box);
  const lineWidth = selected ? 3 : 1.5;

  return (
    <group matrixAutoUpdate={false} matrix={matrix}>
      {/* Invisible fill mesh for reliable click/hover hit detection */}
      <mesh
        geometry={fillGeo}
        onPointerOver={(e) => { e.stopPropagation(); onHover(box); }}
        onPointerOut={() => onUnhover()}
        onClick={(e) => { e.stopPropagation(); onClick?.(box); }}
      >
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
      <lineSegments geometry={edgesGeo}>
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
          background: "rgba(13,17,23,0.92)",
          color: "#ffffff",
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
          <strong style={{ fontSize: 12, color: "#ffffff" }}>{type}</strong>
          <span style={{ fontSize: 10, color: "#9aa0a6" }}>
            {box.source.toUpperCase()} {box.match_type && `· ${box.match_type}`}
          </span>
        </div>
        {box.sde != null && (
          <div style={{
            background: isDangerous ? "rgba(234,67,53,0.12)" : "rgba(28,232,181,0.08)",
            border: `1px solid ${isDangerous ? "#ea4335" : "#1ce8b5"}`,
            borderRadius: 4,
            padding: "4px 8px",
            marginBottom: 4,
            display: "flex",
            justifyContent: "space-between",
          }}>
            <span style={{ color: "#d1d5db" }}>SDE</span>
            <span style={{ fontWeight: 700, color: isDangerous ? "#ea4335" : "#1ce8b5" }}>
              {box.sde.toFixed(3)}m {isDangerous ? "DANGER" : "safe"}
            </span>
          </div>
        )}
        {box.signed_sde != null && (
          <div style={{ fontSize: 10, color: "#6b7280", marginBottom: 2 }}>
            Signed: {box.signed_sde.toFixed(3)}m
            {box.signed_sde > 0 ? " (closer)" : " (farther)"}
          </div>
        )}
        <div style={{ display: "flex", gap: 12, marginTop: 4, color: "#d1d5db" }}>
          {box.iou != null && <span>IoU: <strong>{box.iou.toFixed(3)}</strong></span>}
          {box.confidence != null && <span>Conf: <strong>{box.confidence.toFixed(3)}</strong></span>}
        </div>
        {box.heading_accuracy != null && (
          <div style={{ fontSize: 10, color: "#6b7280", marginTop: 2 }}>
            Heading: {box.heading_accuracy.toFixed(3)}
          </div>
        )}
        {box.range != null && (
          <div style={{ fontSize: 10, color: "#6b7280" }}>
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

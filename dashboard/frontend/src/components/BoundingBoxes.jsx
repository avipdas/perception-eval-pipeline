import { useMemo, useState } from "react";
import * as THREE from "three";
import { Html } from "@react-three/drei";

const TYPE_NAMES = { 1: "VEHICLE", 2: "PEDESTRIAN", 4: "CYCLIST" };

function boxColor(box) {
  if (box.source === "gt") {
    if (box.match_type === "TP") return "#22c55e"; // green — matched GT
    if (box.match_type === "FN") return "#eab308"; // yellow — missed
    return "#6b7280"; // grey — no eval result
  }
  // prediction
  if (box.match_type === "TP") return "#3b82f6"; // blue — matched pred
  if (box.match_type === "FP") return "#ef4444"; // red — hallucination
  return "#6b7280";
}

function WireframeBox({ box, onHover, onUnhover, highlighted }) {
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
  const lineWidth = highlighted ? 3 : 1.5;

  return (
    <group matrixAutoUpdate={false} matrix={matrix}>
      <lineSegments
        geometry={geometry}
        onPointerOver={(e) => {
          e.stopPropagation();
          onHover(box);
        }}
        onPointerOut={() => onUnhover()}
      >
        <lineBasicMaterial color={color} linewidth={lineWidth} />
      </lineSegments>
    </group>
  );
}

function Tooltip({ box }) {
  if (!box) return null;
  const type = TYPE_NAMES[box.object_type] || "UNKNOWN";
  return (
    <Html
      position={[box.center_x, box.center_y, box.center_z + box.height / 2 + 0.5]}
      center
      style={{ pointerEvents: "none" }}
    >
      <div
        style={{
          background: "rgba(0,0,0,0.85)",
          color: "#fff",
          padding: "6px 10px",
          borderRadius: 6,
          fontSize: 11,
          whiteSpace: "nowrap",
          border: `1px solid ${boxColor(box)}`,
        }}
      >
        <strong>{type}</strong> ({box.source.toUpperCase()})
        {box.match_type && <span> — {box.match_type}</span>}
        <br />
        {box.iou != null && <span>IoU: {box.iou.toFixed(3)} &nbsp;</span>}
        {box.sde != null && <span>SDE: {box.sde.toFixed(3)}m &nbsp;</span>}
        {box.confidence != null && (
          <span>Conf: {box.confidence.toFixed(3)}</span>
        )}
        {box.heading_accuracy != null && (
          <>
            <br />
            Heading acc: {box.heading_accuracy.toFixed(3)}
          </>
        )}
      </div>
    </Html>
  );
}

export default function BoundingBoxes({
  boxes,
  showGt = true,
  showPred = true,
  filterTypes = null,
  filterMatch = null,
  highlightId = null,
}) {
  const [hovered, setHovered] = useState(null);

  const filtered = useMemo(() => {
    if (!boxes) return [];
    return boxes.filter((b) => {
      if (b.source === "gt" && !showGt) return false;
      if (b.source === "pred" && !showPred) return false;
      if (filterTypes && !filterTypes.includes(b.object_type)) return false;
      if (filterMatch && b.match_type && !filterMatch.includes(b.match_type))
        return false;
      return true;
    });
  }, [boxes, showGt, showPred, filterTypes, filterMatch]);

  return (
    <group>
      {filtered.map((box, i) => (
        <WireframeBox
          key={`${box.source}-${box.object_id}-${i}`}
          box={box}
          onHover={setHovered}
          onUnhover={() => setHovered(null)}
          highlighted={highlightId === box.object_id}
        />
      ))}
      <Tooltip box={hovered} />
    </group>
  );
}

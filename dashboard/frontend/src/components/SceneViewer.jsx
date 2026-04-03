import { forwardRef, useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, GizmoHelper, GizmoViewport, Html, Line } from "@react-three/drei";
import * as THREE from "three";
import PointCloud from "./PointCloud";
import BoundingBoxes from "./BoundingBoxes";

function EgoMarker() {
  return (
    <group position={[0, 0, 0]}>
      <mesh rotation={[0, 0, -Math.PI / 2]} position={[1.2, 0, 0]}>
        <coneGeometry args={[0.4, 1.2, 8]} />
        <meshStandardMaterial color="#f97316" emissive="#f97316" emissiveIntensity={0.3} />
      </mesh>
      <mesh>
        <boxGeometry args={[2.2, 1.0, 0.6]} />
        <meshStandardMaterial color="#f97316" emissive="#f97316" emissiveIntensity={0.2} transparent opacity={0.6} />
      </mesh>
    </group>
  );
}

function DistanceRing({ radius, color = "#444", label }) {
  const points = useMemo(() => {
    const pts = [];
    for (let i = 0; i <= 128; i++) {
      const a = (i / 128) * Math.PI * 2;
      pts.push(new THREE.Vector3(Math.cos(a) * radius, Math.sin(a) * radius, -1.49));
    }
    return pts;
  }, [radius]);

  return (
    <group>
      <Line points={points} color={color} lineWidth={1} transparent opacity={0.4} />
      <Html position={[radius + 1, 0, -1.49]} center style={{ pointerEvents: "none" }}>
        <span style={{ color: "#666", fontSize: 10, fontFamily: "monospace", whiteSpace: "nowrap" }}>
          {label}
        </span>
      </Html>
    </group>
  );
}

function TrackingTrails({ trailBuffer }) {
  const trails = useMemo(() => {
    if (!trailBuffer || trailBuffer.length < 2) return [];
    const objMap = {};
    trailBuffer.forEach((frameBoxes, fi) => {
      if (!frameBoxes) return;
      frameBoxes
        .filter((b) => b.source === "gt")
        .forEach((b) => {
          if (!objMap[b.object_id]) objMap[b.object_id] = [];
          objMap[b.object_id].push({
            pos: [b.center_x, b.center_y, b.center_z],
            fi,
          });
        });
    });
    return Object.values(objMap)
      .filter((arr) => arr.length >= 2)
      .map((arr) => arr.sort((a, b) => a.fi - b.fi).map((p) => p.pos));
  }, [trailBuffer]);

  return (
    <group>
      {trails.map((pts, i) => (
        <Line
          key={i}
          points={pts}
          color="#f97316"
          lineWidth={2}
          transparent
          opacity={0.5}
        />
      ))}
    </group>
  );
}

const SceneViewer = forwardRef(function SceneViewer(
  {
    pointCloudData,
    boxes,
    showPointCloud,
    showGt,
    showPred,
    filterTypes,
    filterMatch,
    highlightId,
    trailBuffer,
  },
  ref
) {
  return (
    <Canvas
      ref={ref}
      camera={{ position: [0, -40, 30], fov: 60, near: 0.1, far: 500 }}
      style={{ background: "#0f0f0f" }}
      gl={{ preserveDrawingBuffer: true }}
    >
      <ambientLight intensity={0.4} />
      <directionalLight position={[10, 10, 20]} intensity={0.6} />

      <gridHelper
        args={[200, 200, "#333333", "#222222"]}
        rotation={[Math.PI / 2, 0, 0]}
        position={[0, 0, -1.5]}
      />

      <DistanceRing radius={30} color="#3b82f6" label="30m" />
      <DistanceRing radius={50} color="#eab308" label="50m" />
      <DistanceRing radius={75} color="#ef4444" label="75m" />

      <axesHelper args={[5]} />
      <EgoMarker />

      <PointCloud data={pointCloudData} visible={showPointCloud} />
      <BoundingBoxes
        boxes={boxes}
        showGt={showGt}
        showPred={showPred}
        filterTypes={filterTypes}
        filterMatch={filterMatch}
        highlightId={highlightId}
      />

      <TrackingTrails trailBuffer={trailBuffer} />

      <OrbitControls
        enableDamping
        dampingFactor={0.1}
        maxPolarAngle={Math.PI * 0.85}
      />

      <GizmoHelper alignment="bottom-right" margin={[60, 60]}>
        <GizmoViewport labelColor="white" axisHeadScale={0.8} />
      </GizmoHelper>
    </Canvas>
  );
});

export default SceneViewer;

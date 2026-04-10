import { forwardRef, useMemo, useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, GizmoHelper, GizmoViewport, Html, Line } from "@react-three/drei";
import * as THREE from "three";
import PointCloud from "./PointCloud";
import BoundingBoxes from "./BoundingBoxes";

/* ── Ego Vehicle (low-poly sedan + LIDAR pod) ──────────────── */
function EgoVehicle() {
  return (
    <group position={[0, 0, -1.0]}>
      {/* lower body */}
      <mesh position={[0, 0, 0.35]}>
        <boxGeometry args={[4.8, 2.0, 0.7]} />
        <meshStandardMaterial color="#e0e0e0" metalness={0.6} roughness={0.3} />
      </mesh>
      {/* cabin */}
      <mesh position={[-0.3, 0, 1.0]}>
        <boxGeometry args={[2.4, 1.8, 0.65]} />
        <meshStandardMaterial color="#b0bec5" metalness={0.4} roughness={0.4} transparent opacity={0.85} />
      </mesh>
      {/* hood */}
      <mesh position={[1.6, 0, 0.72]} rotation={[0, 0, 0]}>
        <boxGeometry args={[1.2, 1.85, 0.05]} />
        <meshStandardMaterial color="#cfd8dc" metalness={0.5} roughness={0.3} />
      </mesh>
      {/* headlights */}
      <mesh position={[2.35, 0.7, 0.4]}>
        <sphereGeometry args={[0.12, 8, 8]} />
        <meshStandardMaterial color="#fff9c4" emissive="#fff9c4" emissiveIntensity={2} />
      </mesh>
      <mesh position={[2.35, -0.7, 0.4]}>
        <sphereGeometry args={[0.12, 8, 8]} />
        <meshStandardMaterial color="#fff9c4" emissive="#fff9c4" emissiveIntensity={2} />
      </mesh>
      {/* headlight beams */}
      <mesh position={[5, 0.7, 0.4]} rotation={[0, 0, -Math.PI / 2]}>
        <coneGeometry args={[0.6, 5, 8, 1, true]} />
        <meshBasicMaterial color="#fff9c4" transparent opacity={0.04} side={THREE.DoubleSide} />
      </mesh>
      <mesh position={[5, -0.7, 0.4]} rotation={[0, 0, -Math.PI / 2]}>
        <coneGeometry args={[0.6, 5, 8, 1, true]} />
        <meshBasicMaterial color="#fff9c4" transparent opacity={0.04} side={THREE.DoubleSide} />
      </mesh>
      {/* tail lights */}
      <mesh position={[-2.35, 0.75, 0.45]}>
        <sphereGeometry args={[0.1, 8, 8]} />
        <meshStandardMaterial color="#ff5252" emissive="#ff5252" emissiveIntensity={1.5} />
      </mesh>
      <mesh position={[-2.35, -0.75, 0.45]}>
        <sphereGeometry args={[0.1, 8, 8]} />
        <meshStandardMaterial color="#ff5252" emissive="#ff5252" emissiveIntensity={1.5} />
      </mesh>
      {/* roof LIDAR pod */}
      <mesh position={[-0.3, 0, 1.45]}>
        <cylinderGeometry args={[0.25, 0.3, 0.2, 16]} />
        <meshStandardMaterial color="#90a4ae" metalness={0.8} roughness={0.2} />
      </mesh>
      <mesh position={[-0.3, 0, 1.6]}>
        <sphereGeometry args={[0.15, 12, 12]} />
        <meshStandardMaterial color="#00e5ff" emissive="#00e5ff" emissiveIntensity={0.5} metalness={0.3} roughness={0.5} />
      </mesh>
    </group>
  );
}

/* ── Ground Plane with Lane Dashes ─────────────────────────── */
function GroundPlane() {
  const dashes = useMemo(() => {
    const arr = [];
    for (let x = -20; x < 100; x += 6) {
      arr.push(x);
    }
    return arr;
  }, []);

  return (
    <group>
      {/* far ground */}
      <mesh position={[0, 0, -1.52]} rotation={[0, 0, 0]}>
        <planeGeometry args={[300, 300]} />
        <meshStandardMaterial color="#080b1e" />
      </mesh>
      {/* road surface */}
      <mesh position={[20, 0, -1.51]}>
        <planeGeometry args={[200, 12]} />
        <meshStandardMaterial color="#0d1030" />
      </mesh>
      {/* lane lines - left */}
      <mesh position={[20, 3.5, -1.50]}>
        <planeGeometry args={[200, 0.12]} />
        <meshBasicMaterial color="#1e2660" />
      </mesh>
      {/* lane lines - right */}
      <mesh position={[20, -3.5, -1.50]}>
        <planeGeometry args={[200, 0.12]} />
        <meshBasicMaterial color="#1e2660" />
      </mesh>
      {/* center lane dashes */}
      {dashes.map((x) => (
        <mesh key={x} position={[x + 1.5, 0, -1.50]}>
          <planeGeometry args={[3, 0.1]} />
          <meshBasicMaterial color="#2a3380" />
        </mesh>
      ))}
    </group>
  );
}

/* ── Safety Corridor ───────────────────────────────────────── */
function SafetyCorridor({ visible }) {
  const meshRef = useRef();

  useFrame(({ clock }) => {
    if (meshRef.current) {
      meshRef.current.material.opacity = 0.06 + Math.sin(clock.elapsedTime * 2) * 0.02;
    }
  });

  if (!visible) return null;

  return (
    <group>
      <mesh ref={meshRef} position={[25, 0, 0]}>
        <boxGeometry args={[50, 3, 3]} />
        <meshBasicMaterial color="#00e5ff" transparent opacity={0.06} side={THREE.DoubleSide} />
      </mesh>
      <lineSegments position={[25, 0, 0]}>
        <edgesGeometry args={[new THREE.BoxGeometry(50, 3, 3)]} />
        <lineBasicMaterial color="#00e5ff" transparent opacity={0.25} />
      </lineSegments>
    </group>
  );
}

/* ── Distance Rings ────────────────────────────────────────── */
function DistanceRing({ radius, color = "#1e2660", label }) {
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
      <Line points={points} color={color} lineWidth={1} transparent opacity={0.35} />
      <Html position={[radius + 1.5, 0, -1.49]} center style={{ pointerEvents: "none" }}>
        <span style={{ color: "#5c6bc0", fontSize: 9, fontFamily: "'Roboto Mono', monospace", whiteSpace: "nowrap", letterSpacing: "0.5px" }}>
          {label}
        </span>
      </Html>
    </group>
  );
}

/* ── Tracking Trails ───────────────────────────────────────── */
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
        <Line key={i} points={pts} color="#00bcd4" lineWidth={2} transparent opacity={0.4} />
      ))}
    </group>
  );
}

/* ── Main Scene ────────────────────────────────────────────── */
const SceneViewer = forwardRef(function SceneViewer(
  {
    pointCloudData,
    pointCloudMountKey = "pc-0",
    boxes,
    showPointCloud,
    showGt,
    showPred,
    filterTypes,
    filterMatch,
    highlightId,
    trailBuffer,
    showCorridor = false,
    showDistanceRings = true,
    showTrails = true,
    showMotionVectors = true,
    onSelectBox,
    selectedBoxId,
  },
  ref
) {
  return (
    <Canvas
      ref={ref}
      camera={{ position: [-15, 0, 20], fov: 65, near: 0.1, far: 500, up: [0, 0, 1] }}
      style={{ background: "#060920" }}
      gl={{ preserveDrawingBuffer: true }}
      onCreated={({ camera }) => { camera.up.set(0, 0, 1); camera.lookAt(15, 0, 0); }}
    >
      <ambientLight intensity={0.3} />
      <directionalLight position={[10, 10, 20]} intensity={0.5} />
      <directionalLight position={[-10, -10, 15]} intensity={0.15} color="#b388ff" />

      <GroundPlane />

      {showDistanceRings && (
        <>
          <DistanceRing radius={30} color="#1e88e5" label="30 m" />
          <DistanceRing radius={50} color="#7c4dff" label="50 m" />
          <DistanceRing radius={75} color="#ff5252" label="75 m" />
        </>
      )}

      <EgoVehicle />
      <SafetyCorridor visible={showCorridor} />

      <PointCloud key={pointCloudMountKey} data={pointCloudData} visible={showPointCloud} />
      <BoundingBoxes
        boxes={boxes}
        showGt={showGt}
        showPred={showPred}
        filterTypes={filterTypes}
        filterMatch={filterMatch}
        highlightId={highlightId}
        showCorridor={showCorridor}
        showMotionVectors={showMotionVectors}
        onSelectBox={onSelectBox}
        selectedBoxId={selectedBoxId}
      />

      {showTrails && <TrackingTrails trailBuffer={trailBuffer} />}

      <OrbitControls
        target={[15, 0, 0]}
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

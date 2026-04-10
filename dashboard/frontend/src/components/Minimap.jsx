import { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import * as THREE from "three";

const MINIMAP_RANGE = 80;

function MinimapBoxes({ boxes }) {
  const rects = useMemo(() => {
    if (!boxes) return [];
    return boxes.map((b) => {
      let color = "#546e7a";
      if (b.source === "gt") {
        color = b.match_type === "TP" ? "#00e5ff" : b.match_type === "FN" ? "#ffc107" : "#546e7a";
      } else {
        color = b.match_type === "TP" ? "#b388ff" : b.match_type === "FP" ? "#ff5252" : "#546e7a";
      }
      return { ...b, color };
    });
  }, [boxes]);

  return (
    <group>
      {rects.map((b, i) => {
        const mat = new THREE.Matrix4();
        mat.makeRotationZ(b.heading);
        mat.setPosition(b.center_x, b.center_y, 0);
        return (
          <group key={i} matrixAutoUpdate={false} matrix={mat}>
            <mesh>
              <planeGeometry args={[b.length, b.width]} />
              <meshBasicMaterial color={b.color} transparent opacity={0.6} />
            </mesh>
          </group>
        );
      })}
    </group>
  );
}

export default function Minimap({ boxes }) {
  return (
    <div className="minimap">
      <span className="minimap-label">Bird's Eye</span>
      <Canvas
        orthographic
        camera={{
          zoom: 180 / (MINIMAP_RANGE * 2),
          position: [20, 0, 100],
          near: 0.1,
          far: 200,
          up: [0, 1, 0],
        }}
        style={{ background: "#060920" }}
      >
        {/* ground grid */}
        <mesh position={[20, 0, -1]}>
          <planeGeometry args={[MINIMAP_RANGE * 2, MINIMAP_RANGE * 2]} />
          <meshBasicMaterial color="#0a0e27" />
        </mesh>

        {/* range circles */}
        {[30, 50, 75].map((r) => {
          const pts = [];
          for (let i = 0; i <= 64; i++) {
            const a = (i / 64) * Math.PI * 2;
            pts.push(new THREE.Vector3(Math.cos(a) * r, Math.sin(a) * r, 0));
          }
          return (
            <line key={r}>
              <bufferGeometry>
                <bufferAttribute
                  attach="attributes-position"
                  array={new Float32Array(pts.flatMap((p) => [p.x, p.y, p.z]))}
                  count={pts.length}
                  itemSize={3}
                />
              </bufferGeometry>
              <lineBasicMaterial color="#1e2660" transparent opacity={0.5} />
            </line>
          );
        })}

        {/* ego marker */}
        <mesh position={[0, 0, 0]}>
          <circleGeometry args={[1.5, 16]} />
          <meshBasicMaterial color="#e0e0e0" />
        </mesh>
        {/* ego direction */}
        <mesh position={[3, 0, 0]} rotation={[0, 0, -Math.PI / 2]}>
          <coneGeometry args={[0.8, 2, 3]} />
          <meshBasicMaterial color="#e0e0e0" />
        </mesh>

        <MinimapBoxes boxes={boxes} />
      </Canvas>
    </div>
  );
}

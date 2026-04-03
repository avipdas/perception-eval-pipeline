import { useMemo, useRef } from "react";
import * as THREE from "three";

const HEIGHT_MIN = -3;
const HEIGHT_MAX = 4;

export default function PointCloud({ data, visible = true }) {
  const ref = useRef();

  const { positions, colors } = useMemo(() => {
    if (!data || data.count === 0)
      return { positions: new Float32Array(0), colors: new Float32Array(0) };

    const buf = data.buffer;
    const n = data.count;
    const pos = new Float32Array(n * 3);
    const col = new Float32Array(n * 3);

    for (let i = 0; i < n; i++) {
      const x = buf[i * 4 + 0];
      const y = buf[i * 4 + 1];
      const z = buf[i * 4 + 2];

      pos[i * 3 + 0] = x;
      pos[i * 3 + 1] = y;
      pos[i * 3 + 2] = z;

      // Color by height — blue (low) → cyan → green → yellow → red (high)
      const t = Math.max(0, Math.min(1, (z - HEIGHT_MIN) / (HEIGHT_MAX - HEIGHT_MIN)));
      const c = new THREE.Color();
      c.setHSL(0.67 - t * 0.67, 1.0, 0.5);
      col[i * 3 + 0] = c.r;
      col[i * 3 + 1] = c.g;
      col[i * 3 + 2] = c.b;
    }

    return { positions: pos, colors: col };
  }, [data]);

  if (!visible || positions.length === 0) return null;

  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          array={positions}
          count={positions.length / 3}
          itemSize={3}
        />
        <bufferAttribute
          attach="attributes-color"
          array={colors}
          count={colors.length / 3}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.08}
        vertexColors
        sizeAttenuation
        transparent
        opacity={0.85}
      />
    </points>
  );
}

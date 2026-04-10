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

    const cLow = new THREE.Color("#4a148c");
    const cMid = new THREE.Color("#00bcd4");
    const cHigh = new THREE.Color("#e8eaf6");

    for (let i = 0; i < n; i++) {
      const x = buf[i * 4 + 0];
      const y = buf[i * 4 + 1];
      const z = buf[i * 4 + 2];

      pos[i * 3 + 0] = x;
      pos[i * 3 + 1] = y;
      pos[i * 3 + 2] = z;

      const t = Math.max(0, Math.min(1, (z - HEIGHT_MIN) / (HEIGHT_MAX - HEIGHT_MIN)));
      const c = new THREE.Color();
      if (t < 0.5) {
        c.lerpColors(cLow, cMid, t * 2);
      } else {
        c.lerpColors(cMid, cHigh, (t - 0.5) * 2);
      }
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
        size={0.07}
        vertexColors
        sizeAttenuation
        transparent
        opacity={0.9}
      />
    </points>
  );
}

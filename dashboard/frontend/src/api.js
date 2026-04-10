const BASE = "/api";

export async function fetchFrames() {
  const res = await fetch(`${BASE}/frames`);
  return res.json();
}

export async function fetchPointCloud(frameId) {
  const res = await fetch(`${BASE}/frames/${frameId}/point_cloud`, {
    cache: "no-store",
  });
  const buf = await res.arrayBuffer();
  const count = parseInt(res.headers.get("X-Point-Count") || "0", 10);
  return { buffer: new Float32Array(buf), count };
}

export async function fetchBoxes(frameId, runName = "waymo_v1") {
  const res = await fetch(
    `${BASE}/frames/${frameId}/boxes?run_name=${runName}`,
    { cache: "no-store" }
  );
  return res.json();
}

export async function fetchFailures(type = "worst_misses", runName = "waymo_v1") {
  const res = await fetch(
    `${BASE}/failures?type=${type}&run_name=${encodeURIComponent(runName)}&limit=20`,
    { cache: "no-store" }
  );
  return res.json();
}

export async function fetchFrameStats(runName = "waymo_v1") {
  const res = await fetch(`${BASE}/frame_stats?run_name=${encodeURIComponent(runName)}`);
  const data = await res.json();
  const out = {};
  for (const [k, v] of Object.entries(data)) out[Number(k)] = v;
  return out;
}

export async function fetchRuns() {
  const res = await fetch(`${BASE}/runs`);
  return res.json();
}

export async function fetchMetrics(runName = "waymo_v1") {
  const res = await fetch(`${BASE}/metrics?run_name=${runName}`);
  return res.json();
}

export async function fetchPRCurve(runName = "waymo_v1") {
  const res = await fetch(`${BASE}/pr_curve?run_name=${runName}`);
  return res.json();
}

export function cameraUrl(frameId) {
  return `${BASE}/frames/${frameId}/camera`;
}

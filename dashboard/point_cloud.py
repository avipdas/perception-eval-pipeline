"""Extract 3D LiDAR point clouds from Waymo TFRecord range images.

Waymo stores LiDAR data as compressed range images (2D grids where each
pixel holds range, intensity, elongation, and a flag).  This module
decompresses them and converts to Cartesian (x, y, z) point clouds in
the vehicle coordinate frame.

Conversion pipeline per laser:
  1. zlib-decompress the range image bytes
  2. Parse into a MatrixFloat proto  ->  numpy (H, W, 4)
  3. Build inclination / azimuth angle grids from calibration
  4. Spherical-to-Cartesian:  (range, azi, inc)  ->  (x, y, z)
  5. Rotate + translate via the laser's 4x4 extrinsic
  6. Filter out invalid points (range <= 0)
  7. Concatenate all 5 lasers and return (N, 4) with intensity
"""

from __future__ import annotations

import warnings
import zlib
from pathlib import Path
from typing import Optional

import numpy as np
import tensorflow as tf

from waymo_open_dataset import dataset_pb2


# ── helpers ──────────────────────────────────────────────────────────

def _decompress_range_image(raw_bytes: bytes) -> np.ndarray:
    """Decompress and parse a Waymo range image into a numpy array."""
    decompressed = zlib.decompress(raw_bytes)
    matrix = dataset_pb2.MatrixFloat()
    matrix.ParseFromString(decompressed)
    dims = list(matrix.shape.dims)  # [H, W, channels]
    return np.array(matrix.data, dtype=np.float32).reshape(dims)


def _get_beam_inclinations(calibration) -> np.ndarray:
    """Return per-row beam inclination angles for a laser."""
    if len(calibration.beam_inclinations) > 0:
        return np.array(calibration.beam_inclinations, dtype=np.float64)
    # Fall back to min/max interpolation (the proto guarantees one or the other)
    return np.linspace(
        calibration.beam_inclination_min,
        calibration.beam_inclination_max,
        64,
    )


def _range_image_to_points(
    range_image: np.ndarray,
    inclinations: np.ndarray,
    extrinsic: np.ndarray,
) -> np.ndarray:
    """Convert one range image to vehicle-frame points.

    Parameters
    ----------
    range_image : (H, W, C) float32 — channels 0=range, 1=intensity
    inclinations : (H,) float64 — vertical beam angles
    extrinsic : (4, 4) float64 — sensor-to-vehicle transform

    Returns
    -------
    (N, 4) float32 — x, y, z, intensity in vehicle frame
    """
    H, W, _ = range_image.shape
    ranges = range_image[:, :, 0]
    intensity = range_image[:, :, 1]

    # Azimuth: evenly spaced over full 360 deg, from π to −π
    azimuths = np.linspace(np.pi, -np.pi, W, endpoint=False, dtype=np.float64)

    inc_grid, azi_grid = np.meshgrid(inclinations, azimuths, indexing="ij")

    cos_inc = np.cos(inc_grid)
    sin_inc = np.sin(inc_grid)
    cos_azi = np.cos(azi_grid)
    sin_azi = np.sin(azi_grid)

    x = ranges * cos_inc * cos_azi
    y = ranges * cos_inc * sin_azi
    z = ranges * sin_inc

    mask = (ranges > 0) & (ranges < 300)
    pts_sensor = np.stack([x[mask], y[mask], z[mask]], axis=-1)  # (N, 3)
    inten = intensity[mask]  # (N,)

    rotation = extrinsic[:3, :3]
    translation = extrinsic[:3, 3]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        pts_vehicle = (pts_sensor.astype(np.float64) @ rotation.T) + translation

    result = np.column_stack([pts_vehicle.astype(np.float32),
                              inten.astype(np.float32)])

    # Drop any rows with inf/nan from numerical edge cases
    valid = np.isfinite(result).all(axis=1)
    return result[valid]


# ── public API ───────────────────────────────────────────────────────

def extract_point_cloud(frame: dataset_pb2.Frame) -> np.ndarray:
    """Extract the full LiDAR point cloud from a parsed Waymo Frame.

    Combines all laser returns (TOP, FRONT, SIDE_LEFT, SIDE_RIGHT, REAR).

    Returns
    -------
    (N, 4) float32 array — columns are x, y, z, intensity.
    """
    calibrations = {c.name: c for c in frame.context.laser_calibrations}
    all_points: list[np.ndarray] = []

    for laser in frame.lasers:
        ri = laser.ri_return1
        if not ri.range_image_compressed:
            continue

        cal = calibrations[laser.name]
        range_image = _decompress_range_image(ri.range_image_compressed)
        inclinations = _get_beam_inclinations(cal)

        H = range_image.shape[0]
        if len(inclinations) != H:
            inclinations = np.linspace(
                cal.beam_inclination_min, cal.beam_inclination_max, H,
            )

        extrinsic = np.array(cal.extrinsic.transform, dtype=np.float64).reshape(4, 4)
        pts = _range_image_to_points(range_image, inclinations, extrinsic)
        if pts.shape[0] > 0:
            all_points.append(pts)

    if not all_points:
        return np.empty((0, 4), dtype=np.float32)

    return np.concatenate(all_points, axis=0)


def load_frame_from_tfrecord(
    tfrecord_path: str | Path,
    frame_index: int,
) -> dataset_pb2.Frame:
    """Load a specific frame by index from a TFRecord file."""
    dataset = tf.data.TFRecordDataset(str(tfrecord_path), compression_type="")
    for i, record in enumerate(dataset):
        if i == frame_index:
            frame = dataset_pb2.Frame()
            frame.ParseFromString(bytearray(record.numpy()))
            return frame
    raise IndexError(f"Frame index {frame_index} not found in {tfrecord_path}")


def find_tfrecord_for_context(
    context_name: str,
    data_dir: str | Path = "data/raw/waymo",
) -> Optional[Path]:
    """Find the TFRecord file that contains the given context_name."""
    data_dir = Path(data_dir)
    for p in data_dir.glob("*.tfrecord"):
        if context_name in p.name:
            return p
    return None


def extract_front_camera(frame: dataset_pb2.Frame) -> Optional[bytes]:
    """Extract the front camera JPEG from a parsed Frame, or None."""
    for img in frame.images:
        if img.name == 1:  # CameraName.FRONT
            return bytes(img.image)
    return None

"""3D Intersection over Union (IoU) for rotated bounding boxes.

IoU measures how much two boxes overlap:
    IoU = intersection_volume / union_volume

For rotated 3D boxes this requires:
1. Find the intersection polygon of two rotated rectangles (bird's-eye view)
2. Multiply that area by the height overlap to get 3D intersection volume
3. Divide by union volume (vol_a + vol_b - intersection)

The Shapely library handles the polygon intersection geometry for us.
"""

import math
import numpy as np
from shapely.geometry import Polygon


def _box_to_corners_2d(cx, cy, length, width, heading):
    """Compute the 4 corner points of a rotated rectangle in bird's-eye view.

    The box is centred at (cx, cy) with the given length (along the box's
    forward axis) and width (perpendicular). Heading rotates the box.

    Returns an array of shape (4, 2).
    """
    cos_h = math.cos(heading)
    sin_h = math.sin(heading)

    # Half-extents along box-local axes
    half_l = length / 2.0
    half_w = width / 2.0

    # Four corners in the box's local frame, then rotated to world frame
    dx = [half_l, half_l, -half_l, -half_l]
    dy = [half_w, -half_w, -half_w, half_w]

    corners = []
    for lx, ly in zip(dx, dy):
        world_x = cx + lx * cos_h - ly * sin_h
        world_y = cy + lx * sin_h + ly * cos_h
        corners.append((world_x, world_y))

    return corners


def iou_3d(box_a: dict, box_b: dict) -> float:
    """Compute 3D IoU between two boxes.

    Each box is a dict with keys:
        center_x, center_y, center_z, length, width, height, heading

    Returns a float in [0, 1].
    """
    # Step 1: bird's-eye intersection area using Shapely polygons
    corners_a = _box_to_corners_2d(
        box_a["center_x"], box_a["center_y"],
        box_a["length"], box_a["width"], box_a["heading"],
    )
    corners_b = _box_to_corners_2d(
        box_b["center_x"], box_b["center_y"],
        box_b["length"], box_b["width"], box_b["heading"],
    )

    poly_a = Polygon(corners_a)
    poly_b = Polygon(corners_b)

    if not poly_a.intersects(poly_b):
        return 0.0

    inter_area = poly_a.intersection(poly_b).area

    # Step 2: height overlap (1D interval intersection along Z axis)
    a_z_min = box_a["center_z"] - box_a["height"] / 2.0
    a_z_max = box_a["center_z"] + box_a["height"] / 2.0
    b_z_min = box_b["center_z"] - box_b["height"] / 2.0
    b_z_max = box_b["center_z"] + box_b["height"] / 2.0

    z_overlap = max(0.0, min(a_z_max, b_z_max) - max(a_z_min, b_z_min))

    # Step 3: 3D intersection volume
    inter_vol = inter_area * z_overlap

    # Step 4: union = vol_a + vol_b - intersection
    vol_a = box_a["length"] * box_a["width"] * box_a["height"]
    vol_b = box_b["length"] * box_b["width"] * box_b["height"]
    union_vol = vol_a + vol_b - inter_vol

    if union_vol <= 0:
        return 0.0

    return inter_vol / union_vol

"""Support Distance Error (SDE).

From "Revisiting 3D Object Detection From an Egocentric Perspective".

SDE measures how much a prediction error shifts the nearest surface of
a bounding box relative to the ego vehicle.  Unlike IoU, which treats
all box errors equally, SDE focuses on the part of the box that the
ego vehicle would actually interact with — the closest face.

    SDE = |support_dist(prediction) - support_dist(ground_truth)|

Where support_dist is the minimum distance from the ego vehicle (at
the origin) to the box surface.

A small SDE means the error doesn't affect the ego's immediate driving
space.  A large SDE means the nearest surface shifted significantly,
which is safety-critical.
"""

import math


def support_distance(box: dict) -> float:
    """Minimum distance from the ego vehicle (origin) to the box surface.

    Works by transforming the ego position into the box's local coordinate
    frame (where the box is axis-aligned), then computing the closest point
    on the box boundary.

    Parameters
    ----------
    box : dict with center_x, center_y, length, width, heading

    Returns
    -------
    Distance in metres from ego to the nearest face of the box.
    """
    cx = box["center_x"]
    cy = box["center_y"]
    heading = box["heading"]
    half_l = box["length"] / 2.0
    half_w = box["width"] / 2.0

    # Transform ego position (0, 0) into the box's local frame.
    # 1) Translate so the box centre is at the origin
    # 2) Rotate by -heading to undo the box's rotation
    dx = -cx
    dy = -cy
    cos_h = math.cos(heading)
    sin_h = math.sin(heading)
    local_x = dx * cos_h + dy * sin_h
    local_y = -dx * sin_h + dy * cos_h

    # Closest point on the axis-aligned box surface to the ego (in local coords).
    # Clamp the ego's local position to the box extents.
    clamped_x = max(-half_l, min(local_x, half_l))
    clamped_y = max(-half_w, min(local_y, half_w))

    # Distance from ego (in local frame) to that closest surface point
    dist = math.sqrt((local_x - clamped_x) ** 2 + (local_y - clamped_y) ** 2)

    return dist


def compute_sde(gt_box: dict, pred_box: dict) -> float:
    """Compute Support Distance Error between a ground truth and prediction.

    Returns
    -------
    SDE in metres.  Lower is better.
    0.0 means the nearest surface is in exactly the right place.
    """
    return abs(support_distance(pred_box) - support_distance(gt_box))


def compute_signed_sde(gt_box: dict, pred_box: dict) -> float:
    """Signed SDE: positive means the prediction's nearest face is further
    from the ego than reality (the model thinks there's more space than
    there actually is — dangerous underestimate of proximity).

    Negative means the prediction is closer than reality (the model is
    being conservative — less dangerous).
    """
    return support_distance(pred_box) - support_distance(gt_box)

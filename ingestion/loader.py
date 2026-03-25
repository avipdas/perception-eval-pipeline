from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Generator, List

import tensorflow as tf
from waymo_open_dataset import dataset_pb2


# Convert a single Waymo Label protobuf object into a normal Python dict.
# A label represents one annotated object in the frame
def label_to_dict(label: dataset_pb2.Label) -> Dict[str, Any]:
    box = label.box
    meta = label.metadata
    return {
        "id": label.id,
        "type": int(label.type),
        "center_x": box.center_x,
        "center_y": box.center_y,
        "center_z": box.center_z,
        "length": box.length,
        "width": box.width,
        "height": box.height,
        "heading": box.heading,
        "num_lidar_points": label.num_lidar_points_in_box,
        "detection_difficulty": int(label.detection_difficulty_level),
        "tracking_difficulty": int(label.tracking_difficulty_level),
        "speed_x": meta.speed_x,
        "speed_y": meta.speed_y,
        "range": math.sqrt(box.center_x ** 2 + box.center_y ** 2),
    }

# Convert one Waymo Frame protobuf object into a Python dict.
# A frame is one timestamped snapshot of the scene
def frame_to_dict(frame: dataset_pb2.Frame, frame_index: int) -> Dict[str, Any]:
    stats = frame.context.stats
    return {
        "context_name": frame.context.name,
        "timestamp_micros": frame.timestamp_micros,
        "frame_index": frame_index,
        "location": stats.location,
        "weather": stats.weather,
        "time_of_day": stats.time_of_day,
        "laser_labels": [label_to_dict(label) for label in frame.laser_labels],
    }

# Stream frames from a Waymo TFRecord file one at a time.
def load_tfrecord(path: str | Path) -> Generator[Dict[str, Any], None, None]:
    dataset = tf.data.TFRecordDataset(str(path), compression_type="")

    for frame_index, record in enumerate(dataset):
        frame = dataset_pb2.Frame()
        frame.ParseFromString(bytearray(record.numpy()))
        yield frame_to_dict(frame, frame_index)

# Instead of streaming the whole TFRecord, load only the first n frames
# and return them as a list
def load_first_n_frames(path: str | Path, n: int = 3) -> List[Dict[str, Any]]:
    frames: List[Dict[str, Any]] = []
    for i, frame in enumerate(load_tfrecord(path)):
        if i >= n:
            break
        frames.append(frame)
    return frames


if __name__ == "__main__":
    sample_path = Path(
        "data/raw/waymo/individual_files_validation_segment-10203656353524179475_7625_000_7645_000_with_camera_labels.tfrecord"
    )
    # Load only the first 2 frames for quick inspection/debugging.
    frames = load_first_n_frames(sample_path, n=2)
    for frame in frames:
        print(
            f"context={frame['context_name']} "
            f"timestamp={frame['timestamp_micros']} "
            f"num_labels={len(frame['laser_labels'])} "
            f"location={frame['location']} "
            f"weather={frame['weather']} "
            f"time_of_day={frame['time_of_day']}"
        )

        print("\nFirst 3 labels:")
        for label in frame["laser_labels"][:3]:
            print(label)
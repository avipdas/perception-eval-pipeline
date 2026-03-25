"""SQLAlchemy ORM models for the perception evaluation database.

Each class below becomes a SQL table. The hierarchy is:

    Segment  1──*  Frame  1──*  GroundTruth
                         1──*  Prediction

- Segment: one driving run (~20 seconds). Location/weather/time never
  change within a segment, so they live here instead of on every frame.
- Frame: one sensor snapshot. Linked to its parent segment.
- GroundTruth: one human-annotated 3D box. All the fields from label_to_dict.
- Prediction: one model-predicted 3D box. Same shape, plus confidence.
"""

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Segment(Base):
    __tablename__ = "segments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    context_name = Column(String, unique=True, nullable=False, index=True)
    location = Column(String, nullable=True)
    weather = Column(String, nullable=True)
    time_of_day = Column(String, nullable=True)

    frames = relationship("Frame", back_populates="segment")


class Frame(Base):
    __tablename__ = "frames"

    id = Column(Integer, primary_key=True, autoincrement=True)
    segment_id = Column(Integer, ForeignKey("segments.id"), nullable=False, index=True)
    timestamp_micros = Column(Integer, nullable=False)
    frame_index = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("segment_id", "timestamp_micros", name="uq_frame_identity"),
    )

    segment = relationship("Segment", back_populates="frames")
    ground_truths = relationship("GroundTruth", back_populates="frame")
    predictions = relationship("Prediction", back_populates="frame")


class GroundTruth(Base):
    __tablename__ = "ground_truths"

    id = Column(Integer, primary_key=True, autoincrement=True)
    frame_id = Column(Integer, ForeignKey("frames.id"), nullable=False, index=True)

    object_id = Column(String, nullable=False)
    object_type = Column(Integer, nullable=False)

    # 7-DOF 3D bounding box
    center_x = Column(Float, nullable=False)
    center_y = Column(Float, nullable=False)
    center_z = Column(Float, nullable=False)
    length = Column(Float, nullable=False)
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    heading = Column(Float, nullable=False)

    # Precomputed ground-plane distance: sqrt(cx² + cy²)
    range = Column(Float, nullable=False)

    num_lidar_points = Column(Integer, default=0)
    detection_difficulty = Column(Integer, default=0)
    tracking_difficulty = Column(Integer, default=0)
    speed_x = Column(Float, default=0.0)
    speed_y = Column(Float, default=0.0)

    __table_args__ = (
        Index("ix_gt_type", "object_type"),
        Index("ix_gt_range", "range"),
    )

    frame = relationship("Frame", back_populates="ground_truths")


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    frame_id = Column(Integer, ForeignKey("frames.id"), nullable=False, index=True)

    object_type = Column(Integer, nullable=False)
    confidence = Column(Float, nullable=False)

    # Same 7-DOF box as GroundTruth
    center_x = Column(Float, nullable=False)
    center_y = Column(Float, nullable=False)
    center_z = Column(Float, nullable=False)
    length = Column(Float, nullable=False)
    width = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    heading = Column(Float, nullable=False)

    range = Column(Float, nullable=False)

    __table_args__ = (
        Index("ix_pred_type", "object_type"),
        Index("ix_pred_confidence", "confidence"),
    )

    frame = relationship("Frame", back_populates="predictions")

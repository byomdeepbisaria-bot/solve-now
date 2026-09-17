import uuid
import os
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Enum, Integer, Table, ARRAY, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

from .base import Base

# Use pgvector if available, otherwise fall back to ARRAY(Float)
_USE_PGVECTOR = False
try:
    if os.environ.get("PGVECTOR_ENABLED", "").lower() != "false":
        from pgvector.sqlalchemy import Vector as _Vector
        _USE_PGVECTOR = True
except Exception:
    pass

EmbeddingColumn = _Vector(768) if _USE_PGVECTOR else ARRAY(Float)

class ProblemStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    AI_PROCESSING = "AI_PROCESSING"
    OPEN = "OPEN"
    SOLVED = "SOLVED"
    CLOSED = "CLOSED"

class Category(Base):
    __tablename__ = "problem_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String)

problem_tags = Table(
    "problem_tags",
    Base.metadata,
    Column("problem_id", UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
)

class Tag(Base):
    __tablename__ = "tags"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, index=True, nullable=False)

class Problem(Base):
    __tablename__ = "problems"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    public_id = Column(String, unique=True, index=True, nullable=False)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("problem_categories.id"), nullable=True, index=True)
    status = Column(Enum(ProblemStatus), default=ProblemStatus.OPEN, nullable=False, index=True)
    priority = Column(Integer, default=0)
    urgency = Column(String, default="normal")
    is_public = Column(Boolean, default=True, nullable=False, index=True)
    is_hidden = Column(Boolean, default=False, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)

    location = Column(String, nullable=True)

    embedding = Column(EmbeddingColumn, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    solved_at = Column(DateTime(timezone=True), nullable=True)

    author = relationship("User")
    category = relationship("Category")
    tags = relationship("Tag", secondary=problem_tags)
    files = relationship("ProblemFile", back_populates="problem", cascade="all, delete-orphan")
    investigation = relationship("AIInvestigation", back_populates="problem", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        # Composite index for the most common query: public, non-hidden, ordered by date
        {"comment": "Core problem table — see indexes above for query optimization"},
    )

class ScanStatus(str, enum.Enum):
    PENDING = "PENDING"
    CLEAN = "CLEAN"
    INFECTED = "INFECTED"

class ProblemFile(Base):
    __tablename__ = "problem_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id = Column(UUID(as_uuid=True), ForeignKey("problems.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_key = Column(String, nullable=False, unique=True)
    original_name = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    size = Column(Integer, nullable=False)
    sha256 = Column(String, nullable=False, index=True)  # Index for deduplication query
    scan_status = Column(Enum(ScanStatus), default=ScanStatus.PENDING, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    problem = relationship("Problem", back_populates="files")
    owner = relationship("User")


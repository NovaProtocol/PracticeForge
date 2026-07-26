from __future__ import annotations

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class Problem(Base):
    __tablename__ = "problems"

    id = Column(Integer, primary_key=True, autoincrement=True)
    contest_id = Column(Integer, nullable=False)
    problem_index = Column(String(3), nullable=False)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True)
    difficulty_rating = Column(Integer)
    tags = Column(JSON)
    base_code = Column(Text)
    method_name = Column(String(100))
    description_html = Column(Text(length=16777215))
    time_limit = Column(String(100))
    memory_limit = Column(String(100))
    input_spec = Column(Text(length=16777215))
    output_spec = Column(Text(length=16777215))
    notes_html = Column(Text(length=16777215))
    problem_html = Column(Text(length=16777215))
    status = Column(String(20))
    last_scraped_at = Column(DateTime)
    url = Column(String(255))
    regeneration_count = Column(Integer, default=0)
    regeneration_feedback = Column(Text)
    is_interactive = Column(Boolean, default=False)
    examples_json = Column(JSON)
    constraints_json = Column(JSON)
    ai_description_html = Column(Text(length=16777215))
    ai_base_code = Column(Text)
    ai_method_name = Column(String(100))
    created_at = Column(DateTime, server_default=func.current_timestamp())

    __table_args__ = (UniqueConstraint("contest_id", "problem_index"),)

    test_cases = relationship("TestCase", back_populates="problem", cascade="all, delete-orphan")
    solutions = relationship("Solution", back_populates="problem", cascade="all, delete-orphan")


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    problem_id = Column(Integer, ForeignKey("problems.id", ondelete="CASCADE"), nullable=False)
    input = Column(Text)
    expected_output = Column(Text)
    is_sample = Column(Boolean, default=False)
    args = Column(JSON)
    expected = Column(JSON)

    problem = relationship("Problem", back_populates="test_cases")


class Solution(Base):
    __tablename__ = "solutions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    problem_id = Column(Integer, ForeignKey("problems.id", ondelete="CASCADE"), nullable=False)
    code = Column(Text, nullable=False)
    language = Column(String(50), default="python")
    verdict = Column(String(50), default="Pending")
    notes = Column(Text)
    passed_count = Column(Integer, default=0)
    total_count = Column(Integer, default=0)
    timing_ms = Column(Integer)
    memory_kb = Column(Integer)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    problem = relationship("Problem", back_populates="solutions")


class ExecutionQueue(Base):
    __tablename__ = "execution_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    problem_id = Column(Integer, ForeignKey("problems.id", ondelete="CASCADE"), nullable=False)
    code = Column(Text, nullable=False)
    method_name = Column(String(100))
    test_cases_json = Column(JSON)
    exec_type = Column(Enum("run", "submit"), default="run")
    status = Column(Enum("queued", "running", "completed", "failed"), default="queued")
    result = Column(Text(length=4294967295))
    stdout = Column(Text)
    error = Column(Text)
    timing_ms = Column(Integer)
    memory_kb = Column(Integer)
    solution_id = Column(Integer)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.current_timestamp())


class AutoSave(Base):
    __tablename__ = "auto_saves"

    problem_id = Column(Integer, ForeignKey("problems.id", ondelete="CASCADE"), primary_key=True)
    code = Column(Text, nullable=False)
    last_ran = Column(Text)
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())


class ApiUsage(Base):
    __tablename__ = "api_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tokens_used = Column(Integer, default=0)
    window_start = Column(DateTime, server_default=func.current_timestamp())
    window_seconds = Column(Integer, default=18000)
    token_limit = Column(Integer, default=1000000)
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

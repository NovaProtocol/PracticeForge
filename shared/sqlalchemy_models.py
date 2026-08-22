from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import LONGBLOB, LONGTEXT
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
    examples_json = Column(JSON)
    constraints_json = Column(JSON)
    solution_code = Column(Text)
    generator_code = Column(Text)
    executor_code = Column(Text)
    hints = Column(JSON)
    url = Column(String(255))
    created_at = Column(DateTime, server_default=func.current_timestamp())

    __table_args__ = (UniqueConstraint("contest_id", "problem_index"),)

    solutions = relationship("Solution", back_populates="problem", cascade="all, delete-orphan")


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
    updated_at = Column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    problem = relationship("Problem", back_populates="solutions")


class ExecutionQueue(Base):
    __tablename__ = "execution_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    problem_id = Column(Integer, ForeignKey("problems.id", ondelete="CASCADE"), nullable=False)
    code = Column(Text, nullable=False)
    method_name = Column(String(100))
    test_cases_json = Column(JSON)
    exec_type = Column(Enum("run", "submit", "brute_force", "submit_brute"), default="run")
    status = Column(Enum("queued", "running", "completed", "failed"), default="queued")
    result = Column(Text(length=4294967295))
    stdout = Column(Text().with_variant(LONGTEXT, "mysql"))
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
    filename = Column(String(255), primary_key=True, default="main.py")
    code = Column(Text, nullable=False)
    last_ran = Column(Text)
    active = Column(Boolean, default=True)
    updated_at = Column(
        DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp()
    )


class ProblemImage(Base):
    __tablename__ = "problem_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False, unique=True)
    data = Column(LargeBinary().with_variant(LONGBLOB, "mysql"))
    content_type = Column(String(50), default="image/png")
    created_at = Column(DateTime, server_default=func.current_timestamp())

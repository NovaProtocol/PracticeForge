from __future__ import annotations

from shared.db import _engine
from shared.sqlalchemy_models import Base, Problem, TestCase, Solution, ExecutionQueue, AutoSave


def run():
    Base.metadata.create_all(_engine)

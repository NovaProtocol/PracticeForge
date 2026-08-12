from __future__ import annotations

from shared.db import get_engine
from shared.sqlalchemy_models import Base, Problem, Solution, ExecutionQueue, AutoSave


def run():
    Base.metadata.create_all(get_engine())

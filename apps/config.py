from __future__ import annotations

import os


class BaseConfig:
    SECRET_KEY = os.environ["SECRET_KEY"]


class DebugConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False


config_dict = {
    "Debug": DebugConfig,
    "Production": ProductionConfig,
}

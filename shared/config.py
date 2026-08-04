from __future__ import annotations


class BaseConfig:
    pass


class DebugConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False


config_dict = {
    "Debug": DebugConfig,
    "Production": ProductionConfig,
}

from __future__ import annotations


class BaseConfig:
    pass


class ProductionConfig(BaseConfig):
    DEBUG = False

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Shared settings — BaseSettings without min_length (no JWT/sessions in SolveSpace).

    When SECRET_KEY is not used for JWT/sessions,
    omit Field(min_length=32). See task §2.
    """

    DEPLOYMENT_TYPE: str = Field(default="debug")
    MYSQL_HOST: str = Field(default="mysql")
    MYSQL_PORT: int = Field(default=3306)
    MYSQL_USER: str = Field(default="root")
    MYSQL_PASS: str = Field(default="")
    MYSQL_DATABASE: str = Field(default="solvespace")
    API_TOKEN: str = Field(default="")
    EXECUTOR_GRPC_ADDR: str = Field(default="solver_executor:50051")
    GRPC_PORT: int = Field(default=50051)
    SHARED_STATIC_DIR: str = Field(default="")
    SHARED_TEMPLATES_DIR: str = Field(default="")
    DATABASE_URL_OVERRIDE: str | None = Field(default=None, validation_alias="DATABASE_URL")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    @property
    def DEBUG(self) -> bool:
        return self.DEPLOYMENT_TYPE.lower() in ("debug", "true", "1", "yes")

    @property
    def db_url(self) -> str:
        if self.DATABASE_URL_OVERRIDE:
            return self.DATABASE_URL_OVERRIDE
        # sync DSN default — _async_url swaps to aiomysql
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASS}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
        )

    @property
    def async_db_url(self) -> str:
        url = self.db_url
        if url.startswith("sqlite"):
            return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return url.replace("+pymysql", "+aiomysql")


# Backwards-compat aliases
Config = Settings
BaseConfig = Settings
ProductionConfig = Settings


@lru_cache
def get_config() -> Settings:
    # validate DEPLOYMENT_TYPE early — mirrors compose ${VAR:?}
    return Settings()


def shared_static_dir() -> str:
    from pathlib import Path

    candidates = [
        get_config().SHARED_STATIC_DIR,
        "/app/shared/static",
        str(Path(__file__).resolve().parent / "static"),
    ]
    for c in candidates:
        if c and os.path.isdir(c):
            return c
    return candidates[-1]


def shared_templates_dir() -> str:
    from pathlib import Path

    candidates = [
        get_config().SHARED_TEMPLATES_DIR,
        "/app/shared/templates",
        str(Path(__file__).resolve().parent / "templates"),
    ]
    for c in candidates:
        if c and os.path.isdir(c):
            return c
    return candidates[-1]

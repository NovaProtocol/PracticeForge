import sys
from datetime import datetime
from pathlib import Path

from .config import BASE

LOG_PATH = BASE / "scraper.log"


def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _write(level: str, msg: str, file=sys.stdout):
    line = f"[{_ts()}] [{level}] {msg}"
    print(line, file=file, flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def info(msg: str):
    _write("INFO", msg)


def warn(msg: str):
    _write("WARN", msg, file=sys.stderr)


def error(msg: str):
    _write("ERROR", msg, file=sys.stderr)


def debug(msg: str):
    _write("DEBUG", msg)

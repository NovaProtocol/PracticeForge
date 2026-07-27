import sys
from datetime import datetime


def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def info(msg: str):
    print(f"[{_ts()}] [INFO] {msg}", flush=True)


def warn(msg: str):
    print(f"[{_ts()}] [WARN] {msg}", file=sys.stderr, flush=True)


def error(msg: str):
    print(f"[{_ts()}] [ERROR] {msg}", file=sys.stderr, flush=True)


def debug(msg: str):
    print(f"[{_ts()}] [DEBUG] {msg}", flush=True)

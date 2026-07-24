from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

dotenv_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path)

from apps import create_app
from apps.config import config_dict

parser = argparse.ArgumentParser(description="SolveSpace")
parser.add_argument(
    "--deployment-type",
    choices=["DEBUG", "PRODUCTION"],
    default=os.environ.get("DEPLOYMENT_TYPE"),
    help="Run mode ($DEPLOYMENT_TYPE env var, required)",
)
args, _ = parser.parse_known_args()

if not args.deployment_type:
    print(
        "FATAL: DEPLOYMENT_TYPE is not set. Must be DEBUG or PRODUCTION.\n"
        "Set it in your .env file or as an environment variable.",
        file=sys.stderr,
    )
    sys.exit(1)

DEBUG = args.deployment_type == "DEBUG"
get_config_mode = "Debug" if DEBUG else "Production"

try:
    app_config = config_dict[get_config_mode.capitalize()]
except KeyError:
    exit("Error: Invalid <config_mode>. Expected values [Debug, Production]")

app = create_app(app_config)

if __name__ == "__main__":
    if DEBUG:
        app.run(host="0.0.0.0", port=7030, debug=True)
    else:
        try:
            from gunicorn.app.base import BaseApplication
        except ImportError:
            print("gunicorn is not installed. Run: pip install gunicorn", file=sys.stderr)
            sys.exit(1)

        role = os.environ.get("SOLVER_ROLE", "private")
        port = "7030" if role == "public" else "7031"

        class StandaloneApplication(BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()

            def load_config(self):
                for key, value in self.options.items():
                    self.cfg.set(key, value)

            def load(self):
                return self.application

        gunicorn_opts = {
            "bind": f"0.0.0.0:{port}",
            "worker_class": "gthread",
            "workers": 2,
            "threads": 4,
            "accesslog": "-",
            "loglevel": "info",
            "capture_output": True,
            "enable_stdio_inheritance": True,
        }
        StandaloneApplication(app, gunicorn_opts).run()

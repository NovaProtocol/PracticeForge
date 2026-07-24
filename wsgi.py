from __future__ import annotations

import os

os.environ["DEPLOYMENT_TYPE"] = "PRODUCTION"

from run import app

from __future__ import annotations

import logging
import sys

LOGGER_NAME = "ai_part_generator"

logger = logging.getLogger(LOGGER_NAME)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.stream.reconfigure(encoding="utf-8")
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

"""Structured JSON logging. Never log secrets: callers pass identifiers, not credentials."""

import logging
import sys

from pythonjsonlogger.json import JsonFormatter


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s", rename_fields={"asctime": "ts", "levelname": "level"})
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = False  # we emit our own access log (no auth headers)

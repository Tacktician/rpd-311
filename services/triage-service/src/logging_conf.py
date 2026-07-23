"""Minimal JSON logger.

Log lines carry the Raccoon City house tone; enum values, field names, and codes
stay verbatim — they belong to the API contract.
"""
import json
import sys

from .config import config

_LEVELS = {"error": 0, "warning": 1, "warn": 1, "info": 2, "debug": 3}
_threshold = _LEVELS.get(config.log_level.lower(), 2)


def _emit(level: str, message: str, **meta) -> None:
    if _LEVELS.get(level, 2) > _threshold:
        return
    line = {"level": level, "service": "triage-service", "message": message}
    if meta:
        line["meta"] = meta
    stream = sys.stderr if level == "error" else sys.stdout
    print(json.dumps(line), file=stream, flush=True)


class logger:  # noqa: N801 - used as a namespace, mirrors reports-service
    @staticmethod
    def error(message: str, **meta) -> None:
        _emit("error", message, **meta)

    @staticmethod
    def warning(message: str, **meta) -> None:
        _emit("warning", message, **meta)

    @staticmethod
    def info(message: str, **meta) -> None:
        _emit("info", message, **meta)

    @staticmethod
    def debug(message: str, **meta) -> None:
        _emit("debug", message, **meta)

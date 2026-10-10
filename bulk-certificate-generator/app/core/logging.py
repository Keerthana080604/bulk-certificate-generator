"""Logging setup using Python's standard logging module."""
import logging


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if root.handlers:  # already configured (e.g. by uvicorn or pytest)
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

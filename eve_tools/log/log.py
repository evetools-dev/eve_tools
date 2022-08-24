import os
import logging
import sys

if sys.platform == "win32":
    from concurrent_log_handler import ConcurrentRotatingFileHandler
from logging import Logger
from logging.handlers import RotatingFileHandler
from typing import Optional

from eve_tools.config import LOGLEVEL, LOGFILE

FORMATTER = logging.Formatter(
    "%(asctime)s %(levelname)s %(name)s@%(lineno)d: %(message)s"
)
MAXBYTES = 5 * 1024 * 1024
BACKUPCOUNT = 10


# Log levels:
# DEBUG: detailed information, clear workflow
# INFO: conceptual information
# WARNING: unexpected or indicative of future problems
# ERROR: failed some functions, but not crashing
# CRITICAL: crashing


def get_stream_handler():
    handler = logging.StreamHandler()  # stderr
    handler.setLevel(logging.ERROR)
    handler.setFormatter(FORMATTER)
    return handler


def getLogger(
    name: str, filename: Optional[str] = ..., level: Optional[int] = ...
) -> Logger:
    """Returns a logger with specified name and level, using RotatingFileHandler with filename for streaming.

    Args:
        name: str
            Logger name. Used in logging.getLogger(name).
        filename: str | None
            File stream target for RotatingFileHandler. filename is joined using eve_tools/log/{filename}.
            If not given, default "esi.log".
        level: int | None
            Level of the logger. Default WARNING. Default value configured in eve_tools/config/__init__.
    """
    logger = logging.getLogger(name)

    if level is Ellipsis:
        level = LOGLEVEL
    logger.setLevel(level)

    if filename is Ellipsis:
        filename = LOGFILE
    filename = os.path.realpath(os.path.join(os.path.dirname(__file__), filename))

    if sys.platform == "win32":
        file_handler = ConcurrentRotatingFileHandler(filename, maxBytes=MAXBYTES, backupCount=BACKUPCOUNT, delay=True)
    else:  # RotatingFileHandler works on linux/darwin
        file_handler = RotatingFileHandler(
            filename, maxBytes=MAXBYTES, backupCount=BACKUPCOUNT, delay=True  # 5MB * 10
        )
    file_handler.setLevel(level)
    file_handler.setFormatter(FORMATTER)

    logger.addHandler(file_handler)
    logger.addHandler(get_stream_handler())

    logger.propagate = False  # intuitively not necessary

    return logger

from __future__ import absolute_import
import logging

from .api import *
from .ESI import ESIClient, ESITokens, Application
from .data import ESIDB

logging.basicConfig(
    filename="esi.log",
    format="%(asctime)s %(levelname)s %(module)s.%(funcName)s: %(message)s",
    filemode="w",
    level=logging.INFO,
)

__version__ = "0.1.0"

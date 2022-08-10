from __future__ import absolute_import
import os
import logging

from .api import *
from .ESI import ESIClient, ESITokens, Application
from .data import *
from .config import *

logging.basicConfig(
    filename=os.path.join(SOURCE_DIR, "esi.log"),
    format="%(asctime)s %(levelname)s %(module)s.%(funcName)s: %(message)s",
    filemode="w",
    level=logging.WARNING,
)

__version__ = "0.1.2"

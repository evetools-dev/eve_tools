import os

SOURCE_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(SOURCE_DIR, "data")
ESI_DIR = os.path.join(SOURCE_DIR, "ESI")
SSO_DIR = os.path.join(ESI_DIR, "SSO")
TOKEN_PATH = os.path.join(SSO_DIR, "token.json")
APP_PATH = os.path.join(SSO_DIR, "application.json")
METADATA_PATH = os.path.join(ESI_DIR, "metadata.json")

STRUCTURE_MARKET_URL = "https://esi.evetech.net/latest/markets/structures/{}/"

STRUCTURE_ID = {"4-H": 1035466617946}
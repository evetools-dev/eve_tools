import os

SOURCE_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))

# DATA_DIR: src/data/
DATA_DIR = os.path.join(SOURCE_DIR, "data")

# SDE_DIR: src/data/static
SDE_DIR = os.path.join(DATA_DIR, "static")

# ESI_DIR: src/ESI/
ESI_DIR = os.path.join(SOURCE_DIR, "ESI")

# SSO_DIR: src/ESI/sso
SSO_DIR = os.path.join(ESI_DIR, "sso")

# token.json: src/ESI/sso/token.json
TOKEN_PATH = os.path.join(SSO_DIR, "token.json")

# application.json: src/ESI/sso/application.json
APP_PATH = os.path.join(SSO_DIR, "application.json")

# metadata.json: src/ESI/metadata.json
METADATA_PATH = os.path.join(ESI_DIR, "metadata.json")

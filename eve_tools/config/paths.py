import os

# SOURCE_DIR: eve_tools/
SOURCE_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))

# DATA_DIR: eve_tools/data/
DATA_DIR = os.path.join(SOURCE_DIR, "data")

# SDE_DIR: eve_tools/data/static
SDE_DIR = os.path.join(DATA_DIR, "static")

# ESI_DIR: eve_tools/ESI/
ESI_DIR = os.path.join(SOURCE_DIR, "ESI")

# SSO_DIR: eve_tools/ESI/sso
SSO_DIR = os.path.join(ESI_DIR, "sso")

# token.json: eve_tools/ESI/sso/token.json
TOKEN_PATH = os.path.join(SSO_DIR, "token.json")

# application.json: eve_tools/ESI/sso/application.json
APP_PATH = os.path.join(SSO_DIR, "application.json")

# metadata.json: eve_tools/ESI/metadata.json
METADATA_PATH = os.path.join(ESI_DIR, "metadata.json")

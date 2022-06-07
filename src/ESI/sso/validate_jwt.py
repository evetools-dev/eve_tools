"""Validates a given JWT token originating from the EVE SSO.

Source: https://github.com/esi/esi-docs/blob/master/examples/python/sso/validate_jwt.py
"""
import logging
import sys

import requests
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

logger = logging.getLogger(__name__)


def validate_eve_jwt(jwt_token) -> dict:
    """Validate a JWT token retrieved from the EVE SSO.

    Args:
        jwt_token: A JWT token originating from the EVE SSO
    Returns
        dict: The contents of the validated JWT token if there are no
              validation errors
    """

    jwk_set_url = "https://login.eveonline.com/oauth/jwks"

    res = requests.get(jwk_set_url)
    res.raise_for_status()

    data = res.json()

    try:
        jwk_sets = data["keys"]
    except KeyError as e:
        logger.warning(
            "The returned JTW payload did not have the expected key {}. "
            "Payload returned from the SSO looks like: {}".format(e, data)
        )
        sys.exit(1)

    jwk_set = next((item for item in jwk_sets if item["alg"] == "RS256"))

    try:
        return jwt.decode(
            jwt_token,
            jwk_set,
            algorithms=jwk_set["alg"],
            issuer="login.eveonline.com",
            audience="EVE Online",  # newly added required field
        )
    except ExpiredSignatureError:
        logger.warning("The JWT token has expired")
        sys.exit(1)
    except JWTError as e:
        logger.warning(f"The JWT signature was invalid: {e}")
        sys.exit(1)

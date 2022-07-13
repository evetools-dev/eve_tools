import base64
import hashlib
import secrets
from typing import Any

from .shared_flow import (
    generate_auth_url,
    send_token_request,
    handle_sso_token_response,
)


def esi_oauth_local(**kwd) -> Any:
    """A local implementation of the OAuth 2.0 native flow.
    Source: https://github.com/esi/esi-docs/blob/master/examples/python/sso/esi_oauth_native.py"""

    callbackURL = kwd.get("callbackURL", "https://localhost/callback/")

    if "clientID" not in kwd.keys() or "scope" not in kwd.keys():
        raise ValueError("ESI Oauth requied field not given.")

    client_id = kwd["clientID"]

    scope = kwd["scope"]

    # Generate the PKCE code challenge
    random = base64.urlsafe_b64encode(secrets.token_bytes(32))
    m = hashlib.sha256()
    m.update(random)
    d = m.digest()
    code_challenge = base64.urlsafe_b64encode(d).decode().replace("=", "")

    generate_auth_url(
        client_id,
        code_challenge,
        scope=scope,
        callbackURL=callbackURL,
    )

    print("\nAuthorizing following scopes:")
    for _scp in scope.split(" "):
        print("\t", _scp)
    print(
        "Authorization url copied to clipboard... Log into your character to grant scopes above."
    )
    auth_code = input("Copy the entire URL and paste it here: ")
    start_index = auth_code.find("?code=") + len("?code=")
    end_index = auth_code.find("&state")  # this identifier might be volatile
    auth_code = auth_code[start_index:end_index]

    code_verifier = random

    form_values = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": auth_code,
        "code_verifier": code_verifier,
    }

    res = send_token_request(form_values)

    return handle_sso_token_response(res)

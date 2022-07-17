"""Contains all shared OAuth 2.0 flow functions for examples

This module contains all shared functions between the two different OAuth 2.0
flows recommended for web based and mobile/desktop applications. The functions
found here are used by the OAuth 2.0 examples contained in this project.

Source: https://github.com/esi/esi-docs/blob/master/examples/python/sso/shared_flow.py
"""
import apt
import logging
import urllib
import requests
import pyperclip as pc
import time
import sys

from .validate_jwt import validate_eve_jwt

logger = logging.getLogger(__name__)


def generate_auth_url(client_id, code_challenge=None, **kwd):
    """Generates the URL for users to visit.

    Args:
        client_id: The client ID of an EVE SSO application
        code_challenge: A PKCE code challenge
    """

    redirect = kwd.get("callbackURL", "https://localhost/callback/")
    scope = kwd.get("scope")

    base_auth_url = "https://login.eveonline.com/v2/oauth/authorize/"
    params = {
        "response_type": "code",
        "redirect_uri": redirect,
        "client_id": client_id,
        "scope": scope,
        "state": "unique-state",
    }

    if code_challenge:
        params.update(
            {"code_challenge": code_challenge, "code_challenge_method": "S256"}
        )

    string_params = urllib.parse.urlencode(params)
    full_auth_url = "{}?{}".format(base_auth_url, string_params)

    # copy auth url to clipboard
    try:
        pc.copy(full_auth_url)
    except pc.PyperclipException as pc_exc:
        if sys.platform == "linux":
            # Pyperclip needs additional dependency on Linux.
            # Either apt-get install xclip or xsel, 
            # or pip install gtk or PyQt4. 
            # xclip tested to be working under Linux penguin.
            db_packages = apt.Cache()
            db_xclip = db_packages.get("xclip", None)
            db_xsel = db_packages.get("xsel", None)
            if db_xclip and db_xsel:  # cache include "xclip"/"xsel" entry
                if not db_xclip.is_installed and not db_xsel.is_installed:
                    # If both not installed
                    logger.error(
                        "Pyperclip NotImplementedError: needs copy/paste mechanism for Linux: xclip or xsel")
                    raise pc.PyperclipException("With linux, xclip or xsel is necessary. Use sudo apt-get xclip or sudo apt-get xsel to install one of them.") from pc_exc
        raise


def send_token_request(form_values, add_headers={}):
    """Sends a request for an authorization token to the EVE SSO.

    Args:
        form_values: A dict containing the form encoded values that should be
                     sent with the request
        add_headers: A dict containing additional headers to send
    Returns:
        requests.Response: A requests Response object
    """

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Host": "login.eveonline.com",
    }

    if add_headers:
        headers.update(add_headers)

    res = requests.post(
        "https://login.eveonline.com/v2/oauth/token",
        data=form_values,
        headers=headers,
    )

    res.raise_for_status()
    return res


def handle_sso_token_response(sso_response: requests.Response):
    """Handles the authorization code response from the EVE SSO.

    Args:
        sso_response: A requests Response object gotten by calling the EVE
                      SSO /v2/oauth/token endpoint
    """

    if sso_response.status_code == 200:
        data = sso_response.json()
        access_token = data["access_token"]
        data["retrieve_time"] = int(time.time())

        jwt = validate_eve_jwt(access_token)

        # Find character name
        character_name = jwt["name"]
        data["character_name"] = character_name

        # Find character_id
        sub = jwt["sub"]
        character_id = int(sub.split(":")[-1])
        data["character_id"] = character_id

        return data
    else:
        logger.warning("SSO token response error.")
        logger.warning("Sent request with url: %s", sso_response.request.url)
        logger.warning("Sent request with body: %s", sso_response.request.body)
        logger.warning("Sent request with headers: %s", sso_response.request.headers)
        logger.warning("SSO response code is: %s", sso_response.status_code)
        logger.warning("SSO response JSON is: %s", sso_response.json())
        sso_response.raise_for_status()

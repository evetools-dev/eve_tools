"""Contains all shared OAuth 2.0 flow functions for examples

This module contains all shared functions between the two different OAuth 2.0
flows recommended for web based and mobile/desktop applications. The functions
found here are used by the OAuth 2.0 examples contained in this project.
"""
import urllib

import requests

import pyperclip as pc
from six import print_
from pathlib import Path

import json
import time

from .validate_jwt import validate_eve_jwt


def print_auth_url(client_id, code_challenge=None, print_text=False):
    """Prints the URL to redirect users to.

    Args:
        client_id: The client ID of an EVE SSO application
        code_challenge: A PKCE code challenge
    """

    base_auth_url = "https://login.eveonline.com/v2/oauth/authorize/"
    params = {
        "response_type": "code",
        "redirect_uri": "https://localhost/callback/",
        "client_id": client_id,
        "scope": "esi-wallet.read_character_wallet.v1 esi-assets.read_assets.v1 esi-markets.structure_markets.v1 esi-industry.read_character_jobs.v1 esi-markets.read_character_orders.v1 esi-characters.read_blueprints.v1 esi-wallet.read_corporation_wallets.v1",
        "state": "unique-state"
    }

    if code_challenge:
        params.update({
            "code_challenge": code_challenge,
            "code_challenge_method": "S256"
        })

    string_params = urllib.parse.urlencode(params)
    full_auth_url = "{}?{}".format(base_auth_url, string_params)
    
    # copy auth url to clipboard
    pc.copy(full_auth_url)
    print("Authorization url copied to clipboard.")

    if print_text:
        print("\nOpen the following link in your browser:\n\n {} \n\n Once you "
            "have logged in as a character you will get redirected to "
            "https://localhost/callback/.".format(full_auth_url))



def send_token_request(form_values, add_headers={}, print_text=False):
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
    
    if print_text:
        print("Request sent to URL {} with headers {} and form values: "
            "{}\n".format(res.url, headers, form_values))

    res.raise_for_status()

    return res


def handle_sso_token_response(sso_response, print_text=False):
    """Handles the authorization code response from the EVE SSO.

    Args:
        sso_response: A requests Response object gotten by calling the EVE
                      SSO /v2/oauth/token endpoint
    """

    if sso_response.status_code == 200:
        data = sso_response.json()
        access_token = data["access_token"]
        data['retrieve_time'] = int(time.time())

        if print_text:  print("\nVerifying access token JWT...")

        jwt = validate_eve_jwt(access_token)

        with open((Path(__file__) / "../token.json").resolve(), "w") as token_json:
            json.dump(data, token_json)

        character_id = jwt["sub"].split(":")[2]
        character_name = jwt["name"]
        blueprint_path = ("https://esi.evetech.net/latest/characters/{}/"
                          "blueprints/".format(character_id))
        if print_text: 
            print("\nSuccess! Here is the payload received from the EVE SSO: {}"
                "\nYou can use the access_token to make an authenticated "
                "request to {}".format(data, blueprint_path))

        # input("\nPress any key to have this program make the request for you:")
        
        headers = {
            "Authorization": "Bearer {}".format(access_token)
        }

        res = requests.get(blueprint_path, headers=headers)
        if print_text:
            print("\nMade request to {} with headers: "
                "{}".format(blueprint_path, res.request.headers))
        res.raise_for_status()

        data = res.json()
        if print_text: print("\n{} has {} blueprints".format(character_name, len(data)))
    else:
        print("\nSomething went wrong! Re read the comment at the top of this "
              "file and make sure you completed all the prerequisites then "
              "try again. Here's some debug info to help you out:")
        print("\nSent request with url: {} \nbody: {} \nheaders: {}".format(
            sso_response.request.url,
            sso_response.request.body,
            sso_response.request.headers
        ))
        print("\nSSO response code is: {}".format(sso_response.status_code))
        print("\nSSO response JSON is: {}".format(sso_response.json()))

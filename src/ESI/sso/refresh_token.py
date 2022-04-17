import requests
import time


def refresh_token(refresh_token: str, clientId: str):

    base_auth_url = "https://login.eveonline.com/v2/oauth/token"

    form_value = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": clientId,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Host": "login.eveonline.com"
    }

    res = requests.post(base_auth_url, data=form_value, headers=headers)

    data = res.json()
    data['retrieve_time'] = time.time()

    print("Token refresh successful!")
    return data

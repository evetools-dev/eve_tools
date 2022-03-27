import requests
import json
import time
from pathlib import Path


def refresh_token():

    base_auth_url = "https://login.eveonline.com/v2/oauth/token"

    token_json_path = (Path(__file__) / "../token.json").resolve()  # path to the user's private token
    with open(token_json_path, "r") as token_json:
        data = json.load(token_json)  
        refresh_token = data['refresh_token']

    form_value = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": "d759a0558e90469fb46a767f6d05670b"
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Host": "login.eveonline.com"
    }

    res = requests.post(base_auth_url, data=form_value, headers=headers)

    data = res.json()
    data['retrieve_time'] = time.time()
    
    with open(token_json_path, "w") as token_json:
        json.dump(data, token_json)

    print("Token refresh successful!")
    return data

# refresh_token()
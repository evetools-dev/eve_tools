import os
import requests
import json
import time
import pandas as pd

from requests.exceptions import HTTPError

from sso.refresh_token import refresh_token


STRUCTURE_MARKET_URL = "https://esi.evetech.net/latest/markets/structures/1035466617946/"
TOKEN_PATH = os.path.join(os.path.dirname(__file__), 'sso', 'token.json')

def get_headers():
    with open(TOKEN_PATH) as token_json:
        token = json.load(token_json)
    
    time_delta = int(time.time()) - token['retrieve_time']
    if time_delta >= 1200:
        token = refresh_token()

    access_token = token['access_token']
    headers = {
        "Authorization": "Bearer {}".format(access_token)
    }
    return headers

def sync_requests(pages):
    responses = []

    print("Total pages: " + str(pages))

    headers = get_headers()    

    for page in range(2, pages+1):
        req = requests.get(STRUCTURE_MARKET_URL, params={'page': page}, headers=headers)
        responses.append(req)
    
    return responses

def retrieve_structure_market_data():
    if not os.path.exists(TOKEN_PATH):
        from sso.esi_oauth_native import get_code_challenge
        get_code_challenge()

    STRUCTURE_MARKET_FILE_PATH = os.path.join(os.path.dirname(__file__), 'data', 'structure_market_data.csv')

    if os.path.exists(STRUCTURE_MARKET_FILE_PATH):
        last_modified = os.path.getmtime(STRUCTURE_MARKET_FILE_PATH)
        if time.time() - last_modified < 1200:  # update every 20 minutes
            return pd.read_csv(STRUCTURE_MARKET_FILE_PATH, index_col="Unnamed: 0")
        

    all_orders = []
    headers = get_headers()
    res = requests.get(STRUCTURE_MARKET_URL, headers=headers)
    res.raise_for_status()

    all_orders.extend(res.json())
    pages = int(res.headers['X-Pages'])
    responses = sync_requests(pages)

    for response in responses:
        try:
            response.raise_for_status()
        except HTTPError:
            print('Received status code {} from {}'.format(response.status_code, response.url))
            continue

        data = response.json()
        all_orders.extend(data)

    print('Got {:,d} orders.'.format(len(all_orders))) 

    df = pd.DataFrame(all_orders)

    # drop unncessary columns
    df = df.drop(["duration", "location_id", "min_volume", "order_id", "range", "issued", "volume_total"], axis=1)

    # filter out sell orders
    df = df[df['is_buy_order'] == False]

    # find minimum Sell price
    df = df.groupby(['type_id'], as_index=False).min()

    df.to_csv(STRUCTURE_MARKET_FILE_PATH)

    return df


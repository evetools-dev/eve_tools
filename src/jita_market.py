import requests
import pandas as pd
import os
import time

from requests.exceptions import HTTPError


def retrieve_jita_market_data(type_ids: list) -> pd.DataFrame:
    
    JITA_System_ID = 30000142

    JITA_MARKET_URL = f"https://api.evemarketer.com/ec/marketstat/json?usesystem={JITA_System_ID}"
    JITA_MARKET_FILE_PATH = os.path.join(os.path.dirname(__file__), 'data', 'jita_market_data.csv')

    if os.path.exists(JITA_MARKET_FILE_PATH):
        last_modified = os.path.getmtime(JITA_MARKET_FILE_PATH)
        if time.time() - last_modified < 1200:  # update every 20 minutes
            return pd.read_csv(JITA_MARKET_FILE_PATH, index_col="Unnamed: 0")

    # search for 200 ids at a time
    n = len(type_ids)
    all_data = []
    for i in range(0, n, 200):
        batch = type_ids[i : min(i+200, n)]
        res = requests.get(JITA_MARKET_URL, params={"typeid": ",".join(batch)})
        try:
            res.raise_for_status()
        except HTTPError:
            print('Received status code {} from batch starting with {}'.format(res.status_code, str(i)))
            continue

        all_data.extend(res.json())
    
    formatted_data = []
    for data in all_data:
        item_price_data = {}
        item_price_data["type_id"] = data["sell"]["forQuery"]["types"][0]
        item_price_data["jita_sell_min"] = data["sell"]["min"]
        formatted_data.append(item_price_data)

    df = pd.DataFrame(formatted_data)
    df.to_csv(JITA_MARKET_FILE_PATH)

    return df
    
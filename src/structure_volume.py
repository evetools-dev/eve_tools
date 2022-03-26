import asyncio
import aiohttp
import os
import json
import pandas as pd
import time

from datetime import datetime


def extract_volume_history(order_history: list) -> tuple(float, float):
    volume_30_days = 0
    volume_7_days = 0

    for i in range(1, len(order_history)+1):
        today = datetime.today()
        order_date = datetime.strptime(order_history[-i]["date"], "%Y-%m-%d")
        time_delta = (today - order_date).days

        volume = order_history[-i]["volume"]
        if time_delta <= 7:
            volume_7_days += volume
        if time_delta <= 30:
            volume_30_days += volume

    return volume_30_days / 30, volume_7_days / 7


async def parse_order_history_async(type_id):
    VALE_OF_SILENCE_REGION_ID = 10000003
    REGION_ORDER_HISTORY_URL = f"https://esi.evetech.net/latest/markets/{VALE_OF_SILENCE_REGION_ID}/history/?datasource=tranquility&type_id="

    try:
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False)) as session:
            # print(f"Requesting type_id = {type_id}")
            async with session.get(REGION_ORDER_HISTORY_URL + str(type_id)) as response:
                res = await response.text()
                # print(f"Finish requesting type_id = {type_id}")
    except asyncio.TimeoutError:
        print(f"Timeout Error at type_id = {type_id}")
        return {"type_id": type_id, "average_volume_30_days": -1, "average_volume_7_days": -1}

    order_history = json.loads(res)
    if len(order_history) <= 30 or (not isinstance(order_history, list)):
        average_volume_30_days = 0
        average_volume_7_days = 0
    else:
        try:
            average_volume_30_days, average_volume_7_days = extract_volume_history(order_history)
        except TypeError:
            print(f"TypeError for type_id = {type_id}")
            average_volume_30_days = 0
            average_volume_7_days = 0
            
    return {"type_id": type_id, "average_volume_30_days": average_volume_30_days, "average_volume_7_days": average_volume_7_days}


def retrieve_structure_volume(type_ids):
    STRUCTURE_VOLUME_FILE_PATH = os.path.join(os.path.dirname(__file__), 'data', 'structure_volume.csv')

    if os.path.exists(STRUCTURE_VOLUME_FILE_PATH):
        last_modified = os.path.getmtime(STRUCTURE_VOLUME_FILE_PATH)
        if time.time() - last_modified < 604800:  # update every week
            return pd.read_csv(STRUCTURE_VOLUME_FILE_PATH, index_col="Unnamed: 0")

    print(f"Total items: {len(type_ids)}")

    volume_count = []
    for i in range(0, len(type_ids), 200):
        loop = asyncio.get_event_loop()
        tasks = [asyncio.ensure_future(parse_order_history_async(type_ids[k])) for k in range(i, min(i+200, len(type_ids)))]
        loop.run_until_complete(asyncio.wait(tasks))
    
        for task in tasks:
            volume_count.append(task.result())

        print(f"Finish processing batch {i} to {min(i+200, len(type_ids))}...")

    
    df = pd.DataFrame(volume_count)
    df = df.astype({"type_id": 'int64'})
    df.to_csv(STRUCTURE_VOLUME_FILE_PATH)

    return df
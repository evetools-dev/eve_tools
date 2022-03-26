import os
import pandas as pd

from structure_market import retrieve_structure_market_data
from jita_market import retrieve_jita_market_data
from structure_volume import retrieve_structure_volume


DELIVERY_FEE = 700
BROKER_FEE = 0.01
TRANSACTION_TAX = 0.048


### Get market data of markets in Jita and 4-H
structure_data = retrieve_structure_market_data()                                           # 4-H market current image
jita_data = retrieve_jita_market_data(structure_data['type_id'].astype(str).tolist())       # JITA market current image
volume_data = retrieve_structure_volume(structure_data['type_id'].astype(str).tolist())     # 4-H market order histories

invTypesPATH = os.path.join(os.path.dirname(__file__), 'data', 'invTypes.csv')
invTypes = pd.read_csv(invTypesPATH, index_col="Unnamed: 0")  # metadata

### Clean data
market_data = structure_data.merge(invTypes)
market_data = market_data.rename(columns={"price": "4H_sell_min"})
market_data["jita_sell_min"] = jita_data["jita_sell_min"]

### Calculate profit factors
market_data["profit_margin"] = 100 * market_data["4H_sell_min"] * (1 - BROKER_FEE - TRANSACTION_TAX) / (market_data["jita_sell_min"] + market_data["packagedVolume"] * DELIVERY_FEE) - 100
market_data = market_data.merge(volume_data)
market_data["profitability(m)"] = round((market_data["4H_sell_min"] * (1 - BROKER_FEE - TRANSACTION_TAX) - market_data["jita_sell_min"] - market_data["packagedVolume"] * DELIVERY_FEE) * market_data["average_volume_7_days"] / 1000000, 2)

### Sort and clean profitability data
market_data = market_data.sort_values(["profitability(m)", "profit_margin"], ascending=False)
market_data = market_data.round(2)

### Decide on the product in both market
market_data = market_data.drop(["type_id", "is_buy_order", "volume_remain", "groupID", "packagedVolume"], axis=1)
market_data = market_data.reindex(columns=["typeName", "4H_sell_min", "jita_sell_min", "average_volume_30_days", "average_volume_7_days", "profit_margin", "profitability(m)"])
market_data.to_csv("result.csv")

### Record the product and shipping info (and the profit)

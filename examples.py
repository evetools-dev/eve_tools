import os
from typing import Optional
import pandas as pd

from eve_tools import *
from eve_tools.api.utils import reduce_volume


DELIVERY_FEE = 700  # isk / m3
BROKER_FEE = 0.01  # brokers fee at player's STRUCTURE
TRANSACTION_TAX = 0.036
RELIST_DISCOUNT = 0.5  # affected by advanced broker's relation skill


def hauling(
    to_structure: str = "4-HWWF - WinterCo. Central Station",
    cname: str = "Hanbie Serine",
    to_local: Optional[bool] = True,
):
    """Calculate hauling profit from Jita to a structure.

    A player can buy from Jita with sell price, deliver using alliance delivery service, then sell on the structure's market.
    This could generate adequate passive income with low periodic time commitment.
    With 2 billion investment, a character can earn 1.5B per month, with 10 minutes / day time commitment.

    Only supports Jita Sell as part of cost; using Jita buy could lower the cost but increase time commitment.
    Only considers structure sell orders; structure buy price could be ridiculously low.

    If you need better flexibility in this example, e.g. uses Jita buy price, plz contact me.

    Args:
        to_structure: A str for the precise name of the destination structure.
        cname; Character name who has docking access to the structure.
        to_local: A bool for whether to store result to the local file hauling.csv.

    Note:
        Result might not be 100% correct. Confirm with Jita & structure market to verify market price and history.
    """
    # Retrieve active orders from Jita
    jita_market = (
        get_jita_market(order_type="sell").groupby("type_id", as_index=False).min()
    )  # min sell price
    jita_market = jita_market.rename(columns={"price": "Jita Sell"})

    # Retrieve active orders from structure
    structure_market = (
        get_structure_market(to_structure, cname)
        .groupby("type_id", as_index=False)
        .min()
    )
    col_ = f"{to_structure[:3]} Sell"
    structure_market = structure_market.rename(columns={"price": col_})

    # Retrieve volume history of the structure
    type_ids = get_structure_types(to_structure, cname)
    structure_volume = get_market_history(
        search_structure_region_id(to_structure, cname), type_ids, reduce_volume
    )

    # type_id -> name
    invTypes = pd.read_csv(os.path.join(SDE_DIR, "invTypes.csv.bz2"))
    invTypes = invTypes.rename(columns={"typeID": "type_id"})

    # type_id -> packaged volume
    invVolumes = pd.read_csv(os.path.join(SDE_DIR, "invVolumes.csv.bz2"))
    invVolumes = invVolumes.rename(
        columns={"typeID": "type_id", "volume": "packagedVolume"}
    )

    # Merge columns
    hauling_data = (
        jita_market[["type_id", "Jita Sell"]]
        .merge(structure_market[["type_id", col_]])
        .merge(invTypes[["type_id", "typeName", "volume"]])
        .merge(invVolumes, how="left", on="type_id")
        .merge(structure_volume.drop(columns="region_id"))
    )
    hauling_data["packagedVolume"] = hauling_data["packagedVolume"].fillna(
        hauling_data["volume"]
    )

    # Calculate profitability
    # Taxes and delivery fee are included.
    # Broker's fee for one order change is included, which is usually < 0.5%
    cost = hauling_data["Jita Sell"] + DELIVERY_FEE * hauling_data["packagedVolume"]
    sale = hauling_data[col_] * (
        1 - BROKER_FEE - TRANSACTION_TAX - BROKER_FEE * (1 - RELIST_DISCOUNT)
    )
    volume = (
        hauling_data["volume_seven_days"]
        / (hauling_data["volume_seven_days"] + hauling_data["volume_thirty_days"])
        * hauling_data["volume_thirty_days"]
        * 2
    )  # averaging 30 & 7 days volume
    hauling_data["Profit(m)"] = round(volume * (sale - cost) / 1e6, 2)
    hauling_data["Profit Margin"] = round((sale / cost - 1) * 100, 2)

    # Cleaning
    hauling_data = hauling_data.sort_values(
        ["Profit(m)", "Profit Margin"], ascending=False, ignore_index=True
    )
    hauling_data = hauling_data.drop(columns=["volume"])

    if to_local:
        hauling_data.to_csv("hauling.csv")

    return hauling_data


if __name__ == "__main__":
    hauling()

# EVE Tools for trading

> Trading tools collection for EVE Online.

_Author: Hanbo Guo_

_Contact: hb.evetools@gmail.com_


## What is EVE Tools

EVE Tools is a Python package that simplifies EVE ESI. The goal is to write easier and faster Python scripts that analyze EVE data for ISK making. 

## Installations

### 0. Have a working Python environment. 
### 1. Install using PyPI
```sh
pip3 install eve_tools
```
-----
or install manually:

1. First download everything under this repo.
2. Run `requirements.txt` file with pip install:
```sh
cd path/to/your/download/eve_tools-master

pip3 install -r requirements.txt
```
3. Run setup code:
```sh
python setup.py install
```
-----
### 2. Sample usage

```python
from eve_tools import ESIClient

resp = ESIClient.get("/markets/{region_id}/orders/", region_id=10000002, type_id=12005)
print(resp.status)  # 200
print(resp.data)
```

This code requests data from _/markets/{region_id}/orders/_ endpoint, by specifying a `region_id` (10000002 for Jita) and a `type_id` (12005 for Ishtar).
It returns a ``ESIResponse`` object, and the payload can be accessed through ``resp.data``.

----

If you want market history of multiple items:

```python
from eve_tools import ESIClient

resp = ESIClient.get("/markets/{region_id}/orders/", async_loop=["type_id"], region_id=10000002, type_id=[12005, 1405])
# resp: [ESIResponse, ESIResponse]
print(len(resp))  # 2
print(type(resp[0]))  # ESIResponse
```

You can use ``async_loop`` argument to specify if you want to loop through, for example, `type_id`. You can potentially give a loooong list of type ids to search for. 

### 3. Run tests

There are some built-in tests to verify if everything works as expected:
```python
from eve_tools.tests import *
import unittest

test_config.set(cname="your character", structure_name="a player structure that you have docking access")
unittest.main()
```

You would see around 20+ tests running. Internet connection is required.
If you witness any error during testing, please [email me](hb.evetools@gmail.com). 

If you see some tests being skipped: 
```
...ss........ss.....

Ran 24 tests in 16.00s

OK (skipped=4)
```
This means either some endpoints are down (which cripples ``api``s), or your test configuration is incorrect. Use ``test_config.set()`` to configure your tests and rerun tests. 

----

PS: if you spot any errors or if you have some advice, feel free to [email me](hb.evetools@gmail.com). You could also send emails to _Hanbie Serine_ in game.

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
or
### 1. Install manually

#### 1.1 Download everything under this repo

#### 1.2 Run `requirements.txt` file with pip install.
```sh
cd path/to/your/download/eve_tools-master

pip3 install -r requirements.txt
```

#### 1.3 Setup
```sh
python setup.py install
```
-----
### 2. Try with `example.py`

Download `examples.py` by cp/paste it to an empty Python file, run it by:
* double clicking it (in Windows)
* or go to a Python IDE to launch it 
* or use cmd line, cd to its directory, run:
```sh
python examples.py
```
You will see the result `hauling.csv` generated in the same directory as `examples.py`.

### 3. Run tests

Go to a Python editor, run the following code:
```python
from eve_tools import *
import unittest

unittest.main()
```

You would see around 20+ tests running. Internet connection is required.
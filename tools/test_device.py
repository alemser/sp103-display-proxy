#!/usr/bin/env python3
"""Testa no computador a descrição da ponte (firmware/device.py).

    python3 tools/test_device.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware"))

import device   # noqa: E402
from amp_state import INPUTS   # noqa: E402

d = json.loads(json.dumps(device.describe("abcd1234")))
assert d["api"] == 1
assert d["bridge_version"] == "abcd1234"
assert d["volume_db"] == {"min": -78.75, "max": 0, "step": 1.25}
assert d["tone_db"] == {"min": -14, "max": 14, "step": 2}
assert [i["name"] for i in d["inputs"]] == list(INPUTS)
assert [i["id"] for i in d["inputs"]] == ["phono", "tuner", "tape_aux", "cd", "dvd", "dab"]
assert d["display"] == {"columns": 16, "rows": 2}
assert "config" in d["features"] and "control" in d["features"]
print("tudo certo")

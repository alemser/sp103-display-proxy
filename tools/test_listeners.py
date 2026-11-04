#!/usr/bin/env python3
"""Testa no computador quem fica ligado no /events (firmware/listeners.py).

    python3 tools/test_listeners.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "firmware"))

from listeners import MAX_LISTENERS, make_room   # noqa: E402

rig, phone, mac, other = "10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4"

a = [(rig, "w1"), (phone, "w2")]
make_room(a, phone)
assert a == [(rig, "w1")], "o mesmo IP tira a conexão antiga e deixa o rig"

a = [(phone, "w1"), (phone, "w2"), (rig, "w3")]
make_room(a, phone)
assert a == [(rig, "w3")], "todas as antigas do IP saem"

a = [(rig, "w1"), (phone, "w2"), (mac, "w3")]
make_room(a, other)
assert a == [(phone, "w2"), (mac, "w3")] and len(a) < MAX_LISTENERS, "cheio: sai a mais antiga"

a = [(rig, "w1")]
make_room(a, phone)
assert a == [(rig, "w1")], "com lugar sobrando, ninguém sai"

a = [(None, "w1"), (None, "w2")]
make_room(a, None)
assert len(a) == 2, "IP desconhecido não conta como o mesmo cliente"
print("tudo certo")

from dataclasses import replace

import pytest

from app.models import load_config, patch_config
from app.network import load_topology
from app.scenarios import load_scenario
from app.sim import initial_state, step
from app.state import Fault


@pytest.fixture(scope="session")
def topo():
    return load_topology()


@pytest.fixture()
def cfg():
    return load_config()


@pytest.fixture()
def scene(topo, cfg):
    return lambda sid, **over: load_scenario(sid, topo, patch_config(cfg, over) if over else cfg)[:2]


def run(state, topo, cfg, n, **kw):
    for _ in range(n):
        state = step(state, topo, cfg, **kw)
    return state


def fault(id_, type_, target, start=0, end=None, **params):
    return Fault(id_, type_, target, params, start, end)

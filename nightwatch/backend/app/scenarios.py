"""Scenario loader: scripted, replayable JSON -> initial SimState."""
from __future__ import annotations

import json

from .models import DATA_DIR, Config, patch_config
from .network import Topology
from .sim import initial_state
from .state import Fault, SimState


def list_scenarios() -> list[dict]:
    out = []
    for p in sorted((DATA_DIR / "scenarios").glob("*.json")):
        d = json.loads(p.read_text())
        out.append({"id": d["id"], "name": d["name"], "description": d["description"],
                    "decision_engine_enabled": d.get("decision_engine_enabled", True)})
    return out


def load_scenario(scenario_id: str, topo: Topology, cfg: Config) -> tuple[SimState, Config, dict]:
    path = DATA_DIR / "scenarios" / f"{scenario_id}.json"
    if not path.exists():
        raise KeyError(scenario_id)
    d = json.loads(path.read_text())
    cfg = patch_config(cfg, d.get("config_overrides", {}))
    flts = tuple(Fault(f["id"], f["type"], f["target"], f.get("params", {}), f["start_min"], f.get("end_min"))
                 for f in d.get("faults", []))
    return initial_state(topo, cfg, d.get("initial"), flts), cfg, d

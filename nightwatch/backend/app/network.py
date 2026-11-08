"""Topology graph + BFS impact tracing. Static; derived entirely from network.json."""
from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from .models import DATA_DIR


@dataclass(frozen=True)
class TankInfo:
    id: str
    capacity: float
    redundant: bool
    initial: float
    role: str = ""


@dataclass(frozen=True)
class PumpInfo:
    id: str
    tank: str
    pipeline: str
    rated_flow: float
    role: str
    standby_for: str | None


@dataclass(frozen=True)
class Topology:
    nodes: dict
    edges: tuple
    tanks: dict
    pumps: dict
    sources: dict  # id -> tank
    pipeline_treatment: dict
    treatments: tuple
    tank_sources: dict
    tank_pumps: dict
    pipeline_pumps: dict
    treatment_pipelines: dict
    standbys_of: dict
    succ: dict
    pred: dict
    _cache: dict = field(default_factory=dict, compare=False, repr=False)

    def kind(self, asset_id: str) -> str:
        return self.nodes[asset_id]["type"]


def load_topology(path: Path | None = None) -> Topology:
    raw = json.loads((path or DATA_DIR / "network.json").read_text())
    nodes = {n["id"]: n for n in raw["nodes"]}
    edges = tuple((e["from"], e["to"], e.get("kind", "flow")) for e in raw["edges"])
    flow_edges = [(a, b) for a, b, k in edges if k == "flow"]

    def kind(i):
        return nodes[i]["type"]

    tanks = {
        i: TankInfo(i, n["capacity_bbl"], n.get("redundant_sensors", False), n["initial_bbl"], n.get("role", ""))
        for i, n in nodes.items() if n["type"] == "tank"
    }
    sources = {b_src: b for b_src, b in ((a, b) for a, b in flow_edges if kind(a) == "source")}
    pump_tank = {b: a for a, b in flow_edges if kind(a) == "tank" and kind(b) == "pump"}
    pump_pl = {a: b for a, b in flow_edges if kind(a) == "pump" and kind(b) == "pipeline"}
    pl_trt = {a: b for a, b in flow_edges if kind(a) == "pipeline" and kind(b) == "treatment"}
    pumps = {
        i: PumpInfo(i, pump_tank[i], pump_pl[i], n["rated_flow_bbl_hr"], n["role"], n.get("standby_for"))
        for i, n in nodes.items() if n["type"] == "pump"
    }

    def group(pairs):
        out: dict = {}
        for k, v in pairs:
            out.setdefault(k, []).append(v)
        return {k: tuple(v) for k, v in out.items()}

    succ: dict = {i: [] for i in nodes}
    pred: dict = {i: [] for i in nodes}
    for a, b, k in edges:
        succ[a].append(b)
        pred[b].append(a)
        if k == "transfer":  # buffer transfer is bidirectional
            succ[b].append(a)
            pred[a].append(b)
    return Topology(
        nodes=nodes, edges=edges, tanks=tanks, pumps=pumps, sources=sources,
        pipeline_treatment=pl_trt,
        treatments=tuple(i for i, n in nodes.items() if n["type"] == "treatment"),
        tank_sources={t: tuple(s for s, tt in sources.items() if tt == t) for t in tanks},
        tank_pumps={t: tuple(p for p, i in pumps.items() if i.tank == t) for t in tanks},
        pipeline_pumps=group((i.pipeline, p) for p, i in pumps.items()),
        treatment_pipelines=group((t, p) for p, t in pl_trt.items()),
        standbys_of=group((i.standby_for, p) for p, i in pumps.items() if i.standby_for),
        succ={k: tuple(v) for k, v in succ.items()},
        pred={k: tuple(v) for k, v in pred.items()},
    )


def _bfs(adj: dict, start: str) -> list[str]:
    seen, order, q = {start}, [], deque([start])
    while q:
        for n in adj[q.popleft()]:
            if n not in seen:
                seen.add(n)
                order.append(n)
                q.append(n)
    return order


def impact(topo: Topology, asset_id: str) -> dict:
    """Ordered upstream/downstream assets (nearest first). Cached per topology."""
    if asset_id not in topo._cache:
        topo._cache[asset_id] = {"upstream": _bfs(topo.pred, asset_id), "downstream": _bfs(topo.succ, asset_id)}
    return topo._cache[asset_id]

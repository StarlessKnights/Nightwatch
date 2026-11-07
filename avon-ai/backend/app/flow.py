"""Flow allocator (pure). Pumps -> pipelines -> treatment, with proportional sharing of every cap."""
from __future__ import annotations

from dataclasses import dataclass

from .network import Topology


@dataclass(frozen=True)
class FlowResult:
    pump_demand: dict
    pump_flow: dict
    pump_limited_by: dict  # None | "pipeline" | "treatment" | "volume"
    pipeline_flow: dict
    treatment_flow: dict
    tank_inflow: dict
    tank_outflow: dict


def _scale(total: float, cap: float) -> float:
    return 1.0 if total <= cap or total <= 0 else max(cap, 0.0) / total


def allocate(
    topo: Topology, *, volumes: dict, pump_on: dict, pump_cf: dict, pipeline_cap: dict,
    treatment_cap: dict, source_rate: dict, dt_h: float, outflow_multiplier: float = 1.0,
) -> FlowResult:
    """All rates in bbl/hr. source_rate is already net of curtailment/shut-in.

    pump_flow = rated * cf (if running+available), then scaled by pipeline cap (shared by pumps on
    that pipeline), then treatment intake (shared across pipelines proportional to demand), then by
    the volume physically available this step. Throttled, never negative.
    """
    demand = {p: (i.rated_flow * pump_cf[p] * outflow_multiplier if pump_on[p] else 0.0) for p, i in topo.pumps.items()}

    pipe_scale = {pl: _scale(sum(demand[p] for p in ps), pipeline_cap[pl]) for pl, ps in topo.pipeline_pumps.items()}
    pipe_after_cap = {pl: sum(demand[p] for p in ps) * pipe_scale[pl] for pl, ps in topo.pipeline_pumps.items()}

    trt_scale = {
        t: _scale(sum(pipe_after_cap[pl] for pl in pls), treatment_cap[t])
        for t, pls in topo.treatment_pipelines.items()
    }
    pl_scale = {pl: pipe_scale[pl] * trt_scale[topo.pipeline_treatment[pl]] for pl in topo.pipeline_pumps}
    pre_vol = {p: demand[p] * pl_scale[i.pipeline] for p, i in topo.pumps.items()}

    vol_scale = {}
    for tank, ps in topo.tank_pumps.items():
        tot = sum(pre_vol[p] for p in ps)
        vol_scale[tank] = 1.0 if tot <= 0 else min(1.0, volumes[tank] / dt_h / tot)

    flow, limited = {}, {}
    for p, i in topo.pumps.items():
        flow[p] = pre_vol[p] * vol_scale[i.tank]
        t_scale = trt_scale[topo.pipeline_treatment[i.pipeline]]
        if demand[p] <= 0:
            limited[p] = None
        elif vol_scale[i.tank] < 1.0:
            limited[p] = "volume"
        elif pipe_scale[i.pipeline] < 1.0 or t_scale < 1.0:
            limited[p] = "pipeline" if pipe_scale[i.pipeline] <= t_scale else "treatment"
        else:
            limited[p] = None

    pipeline_flow = {pl: sum(flow[p] for p in ps) for pl, ps in topo.pipeline_pumps.items()}
    return FlowResult(
        pump_demand=demand, pump_flow=flow, pump_limited_by=limited, pipeline_flow=pipeline_flow,
        treatment_flow={t: sum(pipeline_flow[pl] for pl in pls) for t, pls in topo.treatment_pipelines.items()},
        tank_inflow={t: sum(source_rate[s] for s in ss) for t, ss in topo.tank_sources.items()},
        tank_outflow={t: sum(flow[p] for p in ps) for t, ps in topo.tank_pumps.items()},
    )

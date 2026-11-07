"""Pydantic schemas: config, API requests, and the Recommendation contract (the future LLM reads ONLY this)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class _M(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class TimeCfg(_M):
    dt_min: int
    horizon_min: int
    forecast_series_step_min: int


class Limits(_M):
    LL: float
    L: float
    H: float
    HH: float
    deadband_bbl: float
    on_delay_min: int
    hh_reset_bbl: float
    ll_reset_bbl: float


class InterlockCfg(_M):
    enabled: bool


class ControlCfg(_M):
    standby_start_delay_min: int
    auto_changeover_on_low_flow: bool
    low_flow_pct: float
    low_flow_duration_min: int
    auto_stop_standby: bool


class SensorsCfg(_M):
    disagree_tolerance_bbl: float
    noise_bbl: float


class StatusCfg(_M):
    watch_min: float
    warning_min: float
    critical_min: float
    predictive_alarm_min: float
    predictive_deadband_min: float


class ConsequenceCfg(_M):
    shutin_duration_h: float
    production_value_per_bbl: float
    restart_cost: float
    spill_penalty: float


class DecisionCfg(_M):
    operator_approval_buffer_min: int
    min_margin_bbl: float
    curtailment_options_pct: list[int]
    max_pair_options: int


class ActionsCfg(_M):
    START_STANDBY_PUMP: dict
    REDUCE_PRODUCTION: dict
    DISPATCH_TRUCK: dict


class UiCfg(_M):
    disclaimer: str
    speeds: list[int]
    start_clock: str
    history_points: int
    ws_forecast_min_interval_s: float


class Config(_M):
    time: TimeCfg
    limits: Limits
    interlock: InterlockCfg
    control: ControlCfg
    sensors: SensorsCfg
    status: StatusCfg
    consequence: ConsequenceCfg
    decision: DecisionCfg
    actions: ActionsCfg
    ui: UiCfg


def load_config(path: Path | None = None) -> Config:
    return Config.model_validate(json.loads((path or DATA_DIR / "config.json").read_text()))


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def patch_config(cfg: Config, patch: dict) -> Config:
    """Deep-merge `patch` into cfg and re-validate."""
    return Config.model_validate(_merge(cfg.model_dump(), patch))


# ---- API requests ----
class FaultRequest(BaseModel):
    type: str
    target: str
    params: dict = {}
    end_min: Optional[int] = None


class AssetPatch(BaseModel):
    capacity_factor: Optional[float] = None
    available: Optional[bool] = None


class SpeedRequest(BaseModel):
    x: int


class EngineRequest(BaseModel):
    enabled: bool


# ---- Recommendation contract ----
class TankForecast(BaseModel):
    tank: str
    time_to_H: Optional[float]
    time_to_HH: Optional[float]
    time_to_overflow: Optional[float]
    confidence: str = "deterministic"
    status: str  # normal | watch | warning | critical
    series: list[float] = []  # volume every `series_step_min`, starting now


class Cause(BaseModel):
    asset: str
    evidence_field: str
    value: Any


class CostBreakdown(BaseModel):
    fixed: float
    hourly: float
    production_loss: float
    expected_consequence: float
    total: Optional[float]  # None when the option was rejected before simulation


class Reason(BaseModel):
    code: str
    text: str


class Option(BaseModel):
    action_id: str
    label: str
    feasible: bool
    reason_codes: list[str]
    reasons: list[Reason]
    cost_breakdown: CostBreakdown
    margin_bbl: Optional[float]
    act_by_min: Optional[float]  # absolute sim minute
    act_by_clock: Optional[str]
    lead_time_min: float
    trajectory_summary: Optional[dict]


class Affected(BaseModel):
    upstream: list[str]
    downstream: list[str]
    first_to_limit: Optional[str]


class Recommendation(BaseModel):
    as_of_min: int
    headline: str
    headline_code: str
    status: str
    forecast: dict[str, TankForecast]
    probable_cause: list[Cause]
    affected_assets: Affected
    options: list[Option]
    ranked_option_ids: list[str]
    best_option_id: Optional[str]
    do_nothing_cost: float
    savings: float
    engine_enabled: bool = True

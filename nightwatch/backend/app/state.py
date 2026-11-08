"""Immutable simulation snapshot types. Pure data, no behavior."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

RUNNING, STOPPED, TRIPPED, STARTING = "RUNNING", "STOPPED", "TRIPPED", "STARTING"

AUTO, ADVISORY, OPERATOR, FAULT, ALARM, SYSTEM = "AUTO", "ADVISORY", "OPERATOR", "FAULT", "ALARM", "SYSTEM"

ACTIVE_UNACK, ACTIVE_ACK, CLEARED = "ACTIVE_UNACK", "ACTIVE_ACK", "CLEARED"


@dataclass(frozen=True)
class Event:
    t_min: int
    tag: str
    code: str
    asset: Optional[str] = None
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TankState:
    volume_bbl: float
    level_sensors: dict  # {"A": float|None, "B": float|None}; None = dead transmitter
    reported_bbl: float  # conservative high reading (high-level protection)
    reported_lo_bbl: float  # conservative low reading (low-level protection)


@dataclass(frozen=True)
class PumpState:
    role: str  # duty | standby
    run_state: str
    health: float  # base pump health w (1 = new); faults are layered on top (see faults.effective)
    available: bool
    start_ready_at_min: Optional[int] = None
    auto_started: bool = False
    low_flow_ticks: int = 0


@dataclass(frozen=True)
class SourceState:
    rate_bbl_hr: float
    curtailment_pct: float = 0.0
    curtail_target_pct: float = 0.0
    curtail_rate_pct_per_min: float = 0.0
    shut_in: bool = False
    shed_pct: float = 0.0  # how far the HH protection has actually shed this source (ramps toward 100)


@dataclass(frozen=True)
class PipelineState:
    max_flow: float
    r: float = 1.0  # restriction (1 = clear, higher = blocked)


@dataclass(frozen=True)
class TreatmentState:
    max_intake: float
    intake_factor: float = 1.0


@dataclass(frozen=True)
class InterlockState:
    tripped: bool = False  # HH: inflow shut in
    ll_tripped: bool = False  # LL: pumps stopped (dry-run protection)


@dataclass(frozen=True)
class Fault:
    id: str
    type: str
    target: str
    params: dict
    start_min: int
    end_min: Optional[int] = None
    announced: bool = False  # True when the session already logged the injection


@dataclass(frozen=True)
class Alarm:
    id: str  # "<tag>:<condition>" -> at most one per tag+condition
    tag: str
    condition: str
    priority: int
    kind: str  # PROCESS | SYSTEM | PREDICTIVE
    state: str
    raised_min: int
    cleared_min: Optional[int] = None
    value: Optional[float] = None


@dataclass(frozen=True)
class PendingAction:
    id: str  # option id, e.g. "START_STANDBY_PUMP:CHP-2"
    kind: str
    params: dict
    effective_at_min: int
    approved_min: int


@dataclass(frozen=True)
class SimState:
    t_min: int
    tanks: dict
    pumps: dict
    sources: dict
    pipelines: dict
    treatment: dict
    interlocks: dict
    faults: tuple = ()
    alarms: tuple = ()
    alarm_timers: dict = field(default_factory=dict)
    pending_actions: tuple = ()
    truck_withdrawals: tuple = ()  # (t_min, tank_id, kWh, dispatch_id)
    next_dispatch_id: int = 0
    flows: Any = None  # flow.FlowResult of the last tick
    new_events: tuple = ()  # events produced by the last step (session accumulates the log)
    trip_counts: dict = field(default_factory=dict)
    overflow_bbl: dict = field(default_factory=dict)
    overflow_events: dict = field(default_factory=dict)
    overflowing: frozenset = frozenset()
    curtailed_bbl: float = 0.0

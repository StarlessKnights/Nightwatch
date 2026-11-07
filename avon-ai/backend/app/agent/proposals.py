from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ActionSpec(StrictModel):
    kind: Literal["START_STANDBY_PUMP", "REDUCE_PRODUCTION", "DISPATCH_TRUCK"]
    target: str = Field(min_length=1, max_length=80)
    pct: int | None = Field(default=None, ge=1, le=100)

    def action(self):
        from ..actions import Action
        if self.kind != "REDUCE_PRODUCTION" and self.pct is not None:
            raise ValueError("Percentage only applies to production reduction")
        key = {"START_STANDBY_PUMP": "pump", "REDUCE_PRODUCTION": "source", "DISPATCH_TRUCK": "tank"}[self.kind]
        params = {key: self.target}
        if self.kind == "REDUCE_PRODUCTION":
            if self.pct is None:
                raise ValueError("Production reduction needs a percentage")
            params["pct"] = self.pct
        return Action(self.kind, params)


class ActionProposal(StrictModel):
    actions: list[ActionSpec] = Field(min_length=1, max_length=4)
    evidence_ids: list[str] = Field(min_length=1, max_length=12)


class FaultSpec(StrictModel):
    type: Literal["PUMP_TRIP", "PUMP_DEGRADE", "PUMP_UNAVAILABLE", "PIPELINE_RESTRICTION", "TREATMENT_CONSTRAINT", "INFLOW_SURGE", "LEVEL_SENSOR_FAULT"]
    target: str = Field(min_length=1, max_length=80)
    params: dict[str, Any] = Field(default_factory=dict)


class ScenarioProposal(StrictModel):
    faults: list[FaultSpec] = Field(min_length=1, max_length=4)


class FaultHypothesis(StrictModel):
    fault: FaultSpec
    evidence_ids: list[str] = Field(min_length=1, max_length=12)


class CitedInterpretation(StrictModel):
    text: str = Field(min_length=1, max_length=700)
    evidence_ids: list[str] = Field(min_length=1, max_length=12)


class AgentAnswer(StrictModel):
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    interpretations: list[CitedInterpretation] = Field(default_factory=list, max_length=6)
    concerns: list[CitedInterpretation] = Field(default_factory=list, max_length=6)
    question: str | None = Field(default=None, max_length=400)


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=2000)


class NoteRequest(StrictModel):
    asset_id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=4000)


class ToggleRequest(StrictModel):
    enabled: bool


class EmptyArgs(StrictModel):
    pass


class AssetArgs(StrictModel):
    asset_id: str = Field(min_length=1, max_length=80)


class HistoryArgs(StrictModel):
    asset_id: str | None = None
    limit: int = Field(default=30, ge=1, le=100)


class DecisionRequest(StrictModel):
    run_id: str

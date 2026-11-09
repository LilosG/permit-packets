"""Request model for the EV job."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from permit_packets.core.schemas import HomeLoadsRequest, PropertyPlanRequest


class EvJobRequest(BaseModel):
    customer: str = Field(min_length=1, max_length=120)
    address: str = Field(min_length=1, max_length=200)
    contractor: str = Field(min_length=1, max_length=120)
    license_number: str = Field(min_length=1, max_length=60)
    home: HomeLoadsRequest
    service_amps: int = Field(ge=60, le=800)
    open_breaker_spaces: int = Field(ge=0, le=60)
    charger_amps: int = Field(ge=16, le=80)
    charger_model: str = Field(default="", max_length=120)
    connection: Literal["hardwired", "receptacle"] = "hardwired"
    has_solar: bool = False
    sample_mode: bool = False
    location: Literal["attached_garage", "detached_garage", "exterior_wall"]
    run_ft: int = Field(gt=0, le=500)
    trench_ft: int = Field(default=0, ge=0, le=500)
    city: str | None = Field(default=None, max_length=80)
    state: str | None = Field(default=None, max_length=2)
    jurisdiction_key: str | None = Field(default=None, max_length=40)
    plan: PropertyPlanRequest | None = None

    @model_validator(mode="after")
    def plan_marks_the_panel_and_charger(self) -> "EvJobRequest":
        if self.plan is not None and not {"panel", "charger"} <= self.plan.markers.keys():
            raise ValueError("the plan needs a panel marker and a charger marker")
        return self

    @model_validator(mode="after")
    def trench_fits_the_run(self) -> "EvJobRequest":
        if self.trench_ft > self.run_ft:
            raise ValueError("the trench can't be longer than the whole circuit run")
        return self

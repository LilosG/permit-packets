"""The EV charger job as the form sends it."""
from typing import Literal

from pydantic import Field, model_validator

from permit_packets.core.schemas import HomeLoadsRequest, JobRequestBase


class EvChargerRequest(JobRequestBase):
    home: HomeLoadsRequest
    service_amps: int = Field(ge=60, le=800)
    open_breaker_spaces: int = Field(ge=0, le=60)
    charger_amps: int = Field(ge=16, le=80)
    charger_model: str = Field(default="", max_length=120)
    connection: Literal["hardwired", "receptacle"] = "hardwired"
    has_solar: bool = False
    location: Literal["attached_garage", "detached_garage", "exterior_wall"]
    run_ft: int = Field(gt=0, le=500)
    trench_ft: int = Field(default=0, ge=0, le=500)

    @model_validator(mode="after")
    def plan_marks_the_panel_and_charger(self) -> "EvChargerRequest":
        if self.plan is not None and not {"panel", "charger"} <= self.plan.markers.keys():
            raise ValueError("the plan needs a panel marker and a charger marker")
        return self

    @model_validator(mode="after")
    def trench_fits_the_run(self) -> "EvChargerRequest":
        if self.trench_ft > self.run_ft:
            raise ValueError("the trench can't be longer than the whole circuit run")
        return self

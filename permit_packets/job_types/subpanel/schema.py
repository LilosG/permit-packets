"""The subpanel / feeder job as the form sends it."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from permit_packets.core.schemas import HomeLoadsRequest, JobRequestBase


class SubpanelLoad(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    va: int = Field(ge=1, le=60000)


class SubpanelRequest(JobRequestBase):
    home: HomeLoadsRequest
    service_amps: int = Field(ge=60, le=400)
    open_breaker_spaces: int = Field(ge=0, le=60)
    location: Literal["same_building", "attached_garage", "detached_building"]
    subpanel_amps: Literal[60, 100, 125, 150, 200]
    feeder_breaker_amps: Literal[60, 70, 90, 100, 125, 150, 200]
    material: Literal["copper", "aluminum"] = "aluminum"
    conduit: Literal["PVC", "EMT"] = "PVC"
    run_ft: int = Field(ge=1, le=500)
    trench_ft: int = Field(ge=0, le=500)
    whole_dwelling: bool = False
    subpanel_model: str = Field(default="", max_length=120)
    loads: list[SubpanelLoad] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def breaker_fits_the_subpanel(self) -> "SubpanelRequest":
        if self.feeder_breaker_amps > self.subpanel_amps:
            raise ValueError("the feeder breaker can't be larger than the subpanel's rating")
        return self

    @model_validator(mode="after")
    def trench_is_part_of_the_run(self) -> "SubpanelRequest":
        if self.trench_ft > self.run_ft:
            raise ValueError("the underground part can't be longer than the whole run")
        return self

    @model_validator(mode="after")
    def whole_dwelling_is_in_the_same_building(self) -> "SubpanelRequest":
        if self.whole_dwelling and self.location != "same_building":
            raise ValueError("the whole-dwelling rule only applies to a subpanel in the same building")
        return self

    @model_validator(mode="after")
    def plan_marks_the_panel_and_subpanel(self) -> "SubpanelRequest":
        if self.plan is not None and not {"panel", "subpanel"} <= self.plan.markers.keys():
            raise ValueError("the plan needs a main panel marker and a subpanel marker")
        return self

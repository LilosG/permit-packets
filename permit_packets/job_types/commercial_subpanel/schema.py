"""The commercial subpanel / feeder job as the form sends it."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from permit_packets.core.commercial import DemandBasis, SystemKey
from permit_packets.core.schemas import JobRequestBase


class CommercialLoad(BaseModel):
    """One new load on the subpanel, in kVA."""
    label: str = Field(min_length=1, max_length=60)
    kva: float = Field(gt=0, le=500)
    continuous: bool = False  # runs three hours or more: counted at 125%


class CommercialSubpanelRequest(JobRequestBase):
    system: SystemKey = "208y120"
    service_amps: int = Field(ge=100, le=1200)
    existing_demand_kva: float = Field(ge=0, le=2000)
    demand_basis: DemandBasis = "utility_12_month"
    open_breaker_spaces: int = Field(ge=0, le=84)
    building_use: str = Field(default="", max_length=80)
    location: Literal["inside_building", "exterior_wall", "detached_building"]
    subpanel_amps: Literal[100, 125, 150, 200, 225, 250, 400]
    feeder_breaker_amps: Literal[60, 70, 80, 90, 100, 125, 150, 175, 200, 225, 250, 300]
    material: Literal["copper", "aluminum"] = "copper"
    conduit: Literal["PVC", "EMT"] = "EMT"
    run_ft: int = Field(ge=1, le=500)
    trench_ft: int = Field(default=0, ge=0, le=500)
    subpanel_model: str = Field(default="", max_length=120)
    loads: list[CommercialLoad] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def breaker_fits_the_subpanel(self) -> "CommercialSubpanelRequest":
        if self.feeder_breaker_amps > self.subpanel_amps:
            raise ValueError("the feeder breaker can't be larger than the subpanel's rating")
        return self

    @model_validator(mode="after")
    def trench_is_part_of_the_run(self) -> "CommercialSubpanelRequest":
        if self.trench_ft > self.run_ft:
            raise ValueError("the underground part can't be longer than the whole run")
        return self

    @model_validator(mode="after")
    def plan_marks_the_panel_and_subpanel(self) -> "CommercialSubpanelRequest":
        if self.plan is not None and not {"panel", "subpanel"} <= self.plan.markers.keys():
            raise ValueError("the plan needs a main panel marker and a subpanel marker")
        return self

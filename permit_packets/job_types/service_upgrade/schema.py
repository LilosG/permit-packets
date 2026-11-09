"""The panel / service upgrade job as the form sends it."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from permit_packets.core.schemas import HomeLoadsRequest, JobRequestBase


class PlannedLoad(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    va: int = Field(ge=1, le=60000)


class ServiceUpgradeRequest(JobRequestBase):
    home: HomeLoadsRequest
    scope: Literal["upgrade", "replacement"]
    existing_service_amps: Literal[60, 100, 125, 150, 200]
    new_service_amps: Literal[100, 125, 150, 200, 225]
    equipment: Literal["meter_main", "main_panel"]
    service_drop: Literal["overhead", "underground"]
    relocated: bool = False
    material: Literal["copper", "aluminum"] = "copper"
    conduit: Literal["PVC", "EMT", "none"] = "PVC"
    se_length_ft: int = Field(ge=1, le=200)
    electrodes: list[Literal["rods", "concrete_encased", "water_pipe"]] = Field(min_length=1)
    bus_amps: int = Field(ge=100, le=400)
    panel_model: str = Field(default="", max_length=120)
    existing_brand: Literal["unknown", "federal_pacific", "zinsco", "pushmatic", "challenger"] = "unknown"
    utility: str = Field(default="", max_length=60)
    meter_number: str = Field(default="", max_length=30)
    has_solar: bool = False
    pv_breaker_amps: int = Field(default=0, ge=0, le=100)
    planned_loads: list[PlannedLoad] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def scope_matches_the_service_sizes(self) -> "ServiceUpgradeRequest":
        if self.scope == "upgrade" and self.new_service_amps <= self.existing_service_amps:
            raise ValueError("a service upgrade needs a new service larger than the existing one")
        if self.scope == "replacement" and self.new_service_amps != self.existing_service_amps:
            raise ValueError("a panel replacement keeps the existing service size")
        return self

    @model_validator(mode="after")
    def bus_carries_the_service(self) -> "ServiceUpgradeRequest":
        if self.bus_amps < self.new_service_amps:
            raise ValueError("the panel's bus rating can't be below the new service size")
        return self

    @model_validator(mode="after")
    def electrodes_are_listed_once(self) -> "ServiceUpgradeRequest":
        if len(set(self.electrodes)) != len(self.electrodes):
            raise ValueError("list each grounding electrode once")
        return self

    @model_validator(mode="after")
    def plan_marks_the_meter_and_panel(self) -> "ServiceUpgradeRequest":
        if self.plan is not None and not {"meter", "panel"} <= self.plan.markers.keys():
            raise ValueError("the plan needs a meter marker and a panel marker")
        return self

    @model_validator(mode="after")
    def solar_needs_its_breaker(self) -> "ServiceUpgradeRequest":
        if self.has_solar and self.pv_breaker_amps <= 0:
            raise ValueError("a home with solar needs the PV breaker size")
        return self

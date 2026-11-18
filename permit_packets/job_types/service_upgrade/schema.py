"""The panel / service upgrade job as the form sends it."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from permit_packets.core.schemas import HomeLoadsRequest, JobRequestBase


class PlannedLoad(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    va: int = Field(ge=1, le=60000)


class FedPanelRequest(BaseModel):
    """400 A only: a panel fed from one of the meter-main's two 200 A service disconnects."""
    model: str = Field(default="", max_length=120)
    bus_amps: int = Field(default=200, ge=100, le=400)
    location: str = Field(default="", max_length=80)
    feeder_ft: int = Field(ge=1, le=200)
    existing: bool = False  # the home's existing panel, re-fed from the new meter-main


class EvChargerAddOnRequest(BaseModel):
    """An EV charger installed with the upgrade, on the panel the upgrade installs."""
    charger_model: str = Field(default="", max_length=120)
    charger_amps: Literal[32, 40, 48, 80]
    run_ft: int = Field(ge=1, le=500)
    location: Literal["attached_garage", "detached_garage", "exterior_wall"] = "attached_garage"
    connection: Literal["hardwired", "receptacle"] = "hardwired"
    trench_ft: int = Field(default=0, ge=0, le=500)
    venting_required: bool | None = None

    @model_validator(mode="after")
    def trench_fits_the_run(self) -> "EvChargerAddOnRequest":
        if self.trench_ft > self.run_ft:
            raise ValueError("the EV charger's underground part can't be longer than its run")
        return self


class ServiceUpgradeRequest(JobRequestBase):
    home: HomeLoadsRequest
    scope: Literal["upgrade", "replacement"]
    existing_service_amps: Literal[60, 100, 125, 150, 200]
    new_service_amps: Literal[100, 125, 150, 200, 225, 400]
    equipment: Literal["meter_main", "main_panel"]
    service_drop: Literal["overhead", "underground"]
    relocated: bool = False
    material: Literal["copper", "aluminum"] = "copper"
    conduit: Literal["PVC", "EMT", "RMC", "none"] = "PVC"
    main_outdoors: bool = False  # main_panel only: the new main panel is on an outside wall (230.85)
    se_length_ft: int = Field(ge=1, le=200)
    electrodes: list[Literal["rods", "concrete_encased", "water_pipe"]] = Field(min_length=1)
    bus_amps: int = Field(ge=100, le=400)
    panel_model: str = Field(default="", max_length=120)
    existing_brand: Literal["unknown", "federal_pacific", "zinsco", "pushmatic", "challenger"] = "unknown"
    utility: str = Field(default="", max_length=60)
    meter_number: str = Field(default="", max_length=30)
    has_solar: bool = False
    surge_protection: Literal["type_1", "type_2"] | None = None  # the service SPD (NEC 230.67)
    pv_breaker_amps: int = Field(default=0, ge=0, le=100)
    planned_loads: list[PlannedLoad] = Field(default_factory=list, max_length=4)
    panels: list[FedPanelRequest] = Field(default_factory=list, max_length=2)  # 400 A: panel 1, then panel 2
    ev_charger: EvChargerAddOnRequest | None = None

    @model_validator(mode="after")
    def four_hundred_amps_is_two_disconnects(self) -> "ServiceUpgradeRequest":
        if self.new_service_amps == 400:
            if self.equipment != "meter_main":
                raise ValueError("a 400 A service is a Class 320 meter-main with two 200 A service disconnects")
            if len(self.panels) != 2:
                raise ValueError("a 400 A service needs the two panels its service disconnects feed")
        elif self.panels:
            raise ValueError("panels fed from two service disconnects are only for a 400 A service")
        return self

    @model_validator(mode="after")
    def ev_charger_is_entered_once(self) -> "ServiceUpgradeRequest":
        if self.ev_charger and any(load.label.strip().lower().startswith(("ev", "electric vehicle"))
                                   for load in self.planned_loads):
            raise ValueError("the EV charger is entered twice: remove it from the planned loads")
        return self

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

    @model_validator(mode="after")
    def panel_bus_is_entered_once(self) -> "ServiceUpgradeRequest":
        expected = self.panels[0].bus_amps if self.new_service_amps == 400 and self.panels else self.bus_amps
        if self.panel_bus_amps is not None and self.panel_bus_amps != expected:
            raise ValueError("the panel bus rating is entered twice with different values")
        return self

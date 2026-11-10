"""The 240 V appliance circuit job as the form sends it."""
from typing import Literal

from pydantic import Field, model_validator

from permit_packets.core.schemas import HomeLoadsRequest, JobRequestBase


class ApplianceCircuitRequest(JobRequestBase):
    home: HomeLoadsRequest
    service_amps: int = Field(ge=60, le=400)
    open_breaker_spaces: int = Field(ge=0, le=60)
    appliance: Literal["hot_tub", "sauna", "heat_pump", "mini_split", "other"]
    appliance_model: str = Field(default="", max_length=120)
    nameplate_amps: float | None = Field(default=None, ge=1, le=100)  # hot_tub, other
    heater_kw: float | None = Field(default=None, ge=1, le=15)  # sauna
    mca: float | None = Field(default=None, ge=1, le=100)  # heat_pump, mini_split
    mocp: int | None = Field(default=None, ge=15, le=125)  # heat_pump, mini_split
    manufacturer_breaker: int | None = Field(default=None, ge=15, le=125)  # hot_tub, sauna, other
    continuous: bool = False  # other only: a hot tub and a sauna are always continuous
    needs_neutral: bool | None = None  # default: yes for a hot tub or other, no for the rest
    terminals_75c: bool = False
    location: Literal["indoor", "outdoor", "detached"]
    wiring: Literal["PVC", "EMT", "cable"]
    run_ft: int = Field(ge=1, le=500)
    trench_ft: int = Field(ge=0, le=500)
    gfci: Literal["breaker", "spa_pack", "none"] | None = None  # hot_tub only
    disconnect_distance_ft: int | None = Field(default=None, ge=0, le=200)  # hot_tub only

    @model_validator(mode="after")
    def the_appliance_has_what_it_needs(self) -> "ApplianceCircuitRequest":
        if self.appliance in ("hot_tub", "other") and self.nameplate_amps is None:
            raise ValueError("a hot tub or other 240 V appliance needs the nameplate amps")
        if self.appliance == "sauna" and self.heater_kw is None:
            raise ValueError("a sauna needs the heater size in kW")
        if self.appliance in ("heat_pump", "mini_split") and (self.mca is None or self.mocp is None):
            raise ValueError("a heat pump or mini-split needs the MCA and the max breaker (MOCP) from the nameplate")
        if self.appliance == "hot_tub" and (self.gfci is None or self.disconnect_distance_ft is None):
            raise ValueError("a hot tub needs the GFCI protection and the disconnect distance from the spa")
        return self

    @model_validator(mode="after")
    def trench_is_part_of_the_run(self) -> "ApplianceCircuitRequest":
        if self.trench_ft > self.run_ft:
            raise ValueError("the underground part can't be longer than the whole run")
        return self

    @model_validator(mode="after")
    def mca_fits_under_the_max_breaker(self) -> "ApplianceCircuitRequest":
        if self.mca is not None and self.mocp is not None and self.mca > self.mocp:
            raise ValueError("the MCA can't be larger than the max breaker (MOCP)")
        return self

    @model_validator(mode="after")
    def plan_marks_the_panel_and_appliance(self) -> "ApplianceCircuitRequest":
        if self.plan is not None and not {"panel", "appliance"} <= self.plan.markers.keys():
            raise ValueError("the plan needs a main panel marker and an appliance marker")
        return self

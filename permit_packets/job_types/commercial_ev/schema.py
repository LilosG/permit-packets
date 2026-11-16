"""The commercial Level 2 EV charger job as the form sends it."""
from typing import Literal

from pydantic import Field, model_validator

from permit_packets.core.commercial import DemandBasis, SystemKey
from permit_packets.core.schemas import JobRequestBase


class CommercialEvRequest(JobRequestBase):
    system: SystemKey = "208y120"
    service_amps: int = Field(ge=100, le=1200)
    existing_demand_kva: float = Field(ge=0, le=2000)
    demand_basis: DemandBasis = "utility_12_month"
    open_breaker_spaces: int = Field(ge=0, le=84)
    building_use: str = Field(default="", max_length=80)
    charger_count: int = Field(ge=1, le=20)
    charger_amps: Literal[16, 24, 32, 40, 48, 64, 80] = 40
    charger_model: str = Field(default="", max_length=120)
    location: Literal["parking_lot", "parking_garage", "building_wall"]
    run_ft: int = Field(gt=0, le=500)  # one way, panel to a charger: the longest run
    trench_ft: int = Field(default=0, ge=0, le=500)
    load_management: bool = False
    managed_limit_amps: int | None = Field(default=None, ge=10, le=1200)  # line current the EVEMS holds the chargers to
    accessible_spaces: int | None = Field(default=None, ge=0, le=20)  # None: not answered yet
    charger_venting_required: bool | None = None  # indoor only; None: not answered yet

    @model_validator(mode="after")
    def chargers_are_208_or_240_volts(self) -> "CommercialEvRequest":
        if self.system == "480y277":
            raise ValueError("Level 2 chargers run on 208 or 240 V: a 480Y/277 V building needs a transformer, "
                             "which this packet doesn't cover")
        return self

    @model_validator(mode="after")
    def load_management_has_a_limit(self) -> "CommercialEvRequest":
        if self.load_management and not self.managed_limit_amps:
            raise ValueError("enter the current the energy management system holds the chargers to")
        return self

    @model_validator(mode="after")
    def trench_fits_the_run(self) -> "CommercialEvRequest":
        if self.trench_ft > self.run_ft:
            raise ValueError("the trench can't be longer than the whole circuit run")
        return self

    @model_validator(mode="after")
    def plan_marks_the_panel_and_chargers(self) -> "CommercialEvRequest":
        if self.plan is not None and not {"panel", "charger"} <= self.plan.markers.keys():
            raise ValueError("the plan needs a panel marker and a charger marker")
        return self

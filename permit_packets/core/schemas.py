import base64
import binascii
from typing import Literal

from pydantic import BaseModel, Field

MAX_VA = 60000
MAX_AERIAL_BASE64 = 2_000_000
PlanPoint = tuple[float, float]


class HomeLoadsRequest(BaseModel):
    square_feet: int = Field(gt=0, le=30000)
    small_appliance_circuits: int = Field(default=2, ge=2, le=12)
    laundry_circuits: int = Field(default=1, ge=0, le=3)
    range_va: int = Field(default=0, ge=0, le=MAX_VA)
    cooktop_va: int = Field(default=0, ge=0, le=MAX_VA)
    oven_va: int = Field(default=0, ge=0, le=MAX_VA)
    dryer_va: int = Field(default=0, ge=0, le=MAX_VA)
    water_heater_va: int = Field(default=0, ge=0, le=MAX_VA)
    dishwasher_va: int = Field(default=0, ge=0, le=MAX_VA)
    disposal_va: int = Field(default=0, ge=0, le=MAX_VA)
    microwave_va: int = Field(default=0, ge=0, le=MAX_VA)
    hot_tub_or_pool_va: int = Field(default=0, ge=0, le=MAX_VA)
    other_va: int = Field(default=0, ge=0, le=MAX_VA)
    heating_va: int = Field(default=0, ge=0, le=MAX_VA)
    cooling_va: int = Field(default=0, ge=0, le=MAX_VA)


class PropertyPlanRequest(BaseModel):
    scale_ft_per_in: int = Field(gt=0, le=200)
    markers: dict[str, PlanPoint] = Field(max_length=8)
    route: list[PlanPoint] = Field(default_factory=list, max_length=20)
    buildings: list[list[PlanPoint]] = Field(default_factory=list, max_length=200)
    primary_building: int | None = None
    lot: list[PlanPoint] = Field(default_factory=list, max_length=2000)
    parcel_number: str = Field(default="", max_length=40)
    aerial_base64: str | None = Field(default=None, max_length=MAX_AERIAL_BASE64)
    credits: list[str] = Field(default_factory=list, max_length=6)

    def aerial_bytes(self) -> bytes | None:
        if not self.aerial_base64:
            return None
        try:
            return base64.b64decode(self.aerial_base64, validate=True)
        except binascii.Error as error:
            raise ValueError("the aerial image is not valid") from error


class LookupRequest(BaseModel):
    address: str = Field(min_length=5, max_length=200)


class PropertyViewRequest(BaseModel):
    """A tap on the right house, or a zoom, on the plan already on screen."""
    address: str = Field(min_length=1, max_length=200)
    city: str = Field(default="", max_length=80)
    state: str = Field(default="", max_length=2)
    county_fips: str = Field(default="", max_length=5)
    house_number: str = Field(default="", max_length=12)
    located_by: str = Field(default="street", max_length=10)
    latitude: float = Field(ge=18, le=72)
    longitude: float = Field(ge=-180, le=-60)
    anchor_latitude: float = Field(ge=18, le=72)
    anchor_longitude: float = Field(ge=-180, le=-60)
    scale_ft_per_in: int = Field(gt=0, le=200)
    tap: PlanPoint | None = None
    zoom: Literal[-1, 1] | None = None


class SuggestRequest(BaseModel):
    text: str = Field(min_length=4, max_length=200)


class AerialRequest(BaseModel):
    latitude: float = Field(ge=18, le=72)
    longitude: float = Field(ge=-180, le=-60)
    scale_ft_per_in: int = Field(gt=0, le=200)


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)

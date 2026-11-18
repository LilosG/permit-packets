import base64
import binascii
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from permit_packets.core.panel_data import GEC_FORMAT, parse_gec

MAX_VA = 60000
MAX_AERIAL_BASE64 = 2_000_000
MAX_PHOTOS = 6
MAX_PHOTO_BASE64 = 900_000        # one photo, after the browser shrinks it
MAX_PHOTOS_TOTAL_BASE64 = 3_200_000  # the host caps a request near 4.5 MB, and the PDF call repeats the photos
MAX_PHOTO_PIXELS = 40_000_000
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


class PhotoRequest(BaseModel):
    """A site photo the electrician attaches, for the Photos page. The label says what it shows."""
    label: str = Field(min_length=1, max_length=60)
    caption: str = Field(default="", max_length=120)
    image_base64: str = Field(min_length=100, max_length=MAX_PHOTO_BASE64)

    @field_validator("label", "caption")
    @classmethod
    def trimmed(cls, value: str) -> str:
        return value.strip()

    @field_validator("image_base64")
    @classmethod
    def is_a_jpeg_or_png(cls, value: str) -> str:
        from io import BytesIO

        from PIL import Image, UnidentifiedImageError

        try:
            raw = base64.b64decode(value, validate=True)
            with Image.open(BytesIO(raw)) as image:
                if image.format not in ("JPEG", "PNG"):
                    raise ValueError("photos must be JPEG or PNG")
                if image.width * image.height > MAX_PHOTO_PIXELS:
                    raise ValueError("the photo is too large")
        except (binascii.Error, UnidentifiedImageError, OSError) as error:
            raise ValueError("the photo is not a valid image") from error
        return value

    def image_bytes(self) -> bytes:
        return base64.b64decode(self.image_base64)


class ExistingCircuitRequest(BaseModel):
    """One circuit already in the panel, for the panel schedule."""
    label: str = Field(min_length=1, max_length=60)
    amps: int = Field(ge=15, le=400)
    poles: int = Field(default=1, ge=1, le=3)


class JobRequestBase(BaseModel):
    """What every job type asks for: who it's for, where, and the optional site plan."""
    customer: str = Field(min_length=1, max_length=120)
    address: str = Field(min_length=1, max_length=200)
    contractor: str = Field(min_length=1, max_length=120)
    license_number: str = Field(min_length=1, max_length=60)
    sample_mode: bool = False
    city: str | None = Field(default=None, max_length=80)
    state: str | None = Field(default=None, max_length=2)
    jurisdiction_key: str | None = Field(default=None, max_length=40)
    plan: PropertyPlanRequest | None = None
    photos: list[PhotoRequest] = Field(default_factory=list, max_length=MAX_PHOTOS)
    existing_circuits: list[ExistingCircuitRequest] = Field(default_factory=list, max_length=60)
    sheet_size: Literal["letter", "tabloid", "ansi_d"] | None = None  # None: the city's preference
    # The utility's available fault current at the service, and the panel and breaker interrupting rating.
    available_fault_current_a: int | None = Field(default=None, ge=1, le=200_000)
    equipment_aic_ka: int = Field(default=10, ge=1, le=200)
    # The existing panel, for the panel schedule and the one-line.
    # True when the electrician attaches the manufacturer's data sheet themselves, for equipment that
    # isn't in the library. Library chargers and panels attach their own sheet.
    data_sheet_attached: bool = False
    panel_location: str = Field(default="", max_length=80)
    panel_bus_amps: int | None = Field(default=None, ge=60, le=800)
    panel_main: Literal["main breaker", "main lug"] | None = None
    gec_size: str = Field(default="", max_length=20)  # the existing grounding electrode conductor, e.g. "#4 Cu"

    @field_validator("photos")
    @classmethod
    def photos_fit_in_a_request(cls, photos: list[PhotoRequest]) -> list[PhotoRequest]:
        if sum(len(photo.image_base64) for photo in photos) > MAX_PHOTOS_TOTAL_BASE64:
            raise ValueError("the photos are too large together. Attach fewer or smaller photos")
        return photos

    @field_validator("gec_size")
    @classmethod
    def gec_size_reads_as_a_wire_size(cls, value: str) -> str:
        if value.strip() and parse_gec(value) is None:
            raise ValueError(f"the grounding electrode conductor size isn't readable. {GEC_FORMAT}")
        return value.strip()


class LookupRequest(BaseModel):
    address: str = Field(min_length=5, max_length=200)
    job_type: str = Field(default="ev_charger", max_length=40)


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
    job_type: str = Field(default="ev_charger", max_length=40)


class SuggestRequest(BaseModel):
    text: str = Field(min_length=4, max_length=200)


class AerialRequest(BaseModel):
    latitude: float = Field(ge=18, le=72)
    longitude: float = Field(ge=-180, le=-60)
    scale_ft_per_in: int = Field(gt=0, le=200)


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=200)

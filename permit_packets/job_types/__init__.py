"""The permit types this platform builds.

A job type is one `JobType` value: what the page asks for, what the packet's
documents are, and a function that turns a validated request into a packet.
Register it in REGISTRY; a client sees it once `clients.py` enables it.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class Marker:
    """A spot the tech taps on the plan, drawn as a lettered dot."""
    key: str
    label: str
    letter: str
    color: str
    prompt: str


@dataclass(frozen=True)
class Document:
    """One page of the packet: its file name in the ZIP and its title in the preview."""
    file_stem: str
    title: str


@dataclass(frozen=True)
class PacketResult:
    """The finished PDF and the JSON the page shows beside it (everything but the page images)."""
    pdf: bytes
    body: dict


@dataclass(frozen=True)
class JobType:
    key: str
    slug: str
    label: str
    short_label: str
    blurb: str
    icon: str
    markers: tuple[Marker, ...]
    route_between: tuple[str, str] | None
    uses_home_loads: bool
    documents: tuple[Document, ...]
    feature_page: int  # index of the document shown large in the preview
    request_model: type[BaseModel]
    build_response: Callable[[BaseModel], PacketResult]
    zip_name: str


# Job types import the classes above, so they come after them.
from permit_packets.job_types.appliance_circuit import JOB_TYPE as APPLIANCE_CIRCUIT  # noqa: E402
from permit_packets.job_types.ev_charger import JOB_TYPE as EV_CHARGER  # noqa: E402
from permit_packets.job_types.service_upgrade import JOB_TYPE as SERVICE_UPGRADE  # noqa: E402
from permit_packets.job_types.subpanel import JOB_TYPE as SUBPANEL  # noqa: E402

REGISTRY: dict[str, JobType] = {
    job_type.key: job_type for job_type in (EV_CHARGER, SERVICE_UPGRADE, SUBPANEL, APPLIANCE_CIRCUIT)
}


def get_job_type(slug: str) -> JobType | None:
    return next((job_type for job_type in REGISTRY.values() if job_type.slug == slug), None)

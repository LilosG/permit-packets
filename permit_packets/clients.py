"""Who a deployment is set up for, and which job types they bought."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from permit_packets.job_types import REGISTRY
from permit_packets.jurisdictions import KNOWN

DEFAULT_CLIENT = "demo"


ALL_JOB_TYPES = ("ev_charger", "service_upgrade", "subpanel", "appliance_circuit")
LOGO_DIR = Path(__file__).parent / "static" / "assets" / "logos"


@dataclass(frozen=True)
class Client:
    key: str
    company_name: str
    job_types: tuple[str, ...]
    website: str = ""
    logo: str = ""  # file name under static/assets/logos/; empty prints the company name as text
    jurisdiction_keys: tuple[str, ...] = ()  # the only cities the client can pick; the first is the default
    sheet_size: str | None = None  # overrides the city's sheet size
    single_pdf_only: bool | None = None  # overrides the city's one-PDF rule

    @property
    def is_demo(self) -> bool:
        return self.key == DEFAULT_CLIENT

    def allows(self, jurisdiction_key: str) -> bool:
        return jurisdiction_key in self.jurisdiction_keys

    def logo_bytes(self) -> bytes | None:
        return (LOGO_DIR / self.logo).read_bytes() if self.logo else None

    def sheet_size_for(self, jurisdiction) -> str:
        return self.sheet_size or jurisdiction.sheet_size

    def single_pdf_only_for(self, jurisdiction) -> bool:
        return jurisdiction.single_pdf_only if self.single_pdf_only is None else self.single_pdf_only


def _client(key: str, company: str, website: str, logo: str, city: str) -> Client:
    return Client(key, company, ALL_JOB_TYPES, website, logo, (city,))


CLIENTS: dict[str, Client] = {
    # The demo sees every city, plus the general fallback for any other address.
    "demo": Client("demo", "", ALL_JOB_TYPES, jurisdiction_keys=tuple(j.key for j in KNOWN.values()) + ("general",)),
    "erke": _client("erke", "Erke Electric", "https://er-ke.com", "erke.png", "nashville-tn"),
    "elc": _client("elc", "ELC Contractor LLC", "https://electricelc.com", "elc.png", "san-francisco-ca"),
    "thee-electrician": _client(
        "thee-electrician", "Thee Electrician", "https://theeelectrician.co", "thee.png", "san-francisco-ca"),
    # One city for the trial: Chandler, checked against Chandler's published requirements. More cities are
    # added if JBee signs on.
    "jbee": _client("jbee", "JBee Industries", "https://jbindustrieshvac.com", "jbee.png", "chandler-az"),
    "volta": _client("volta", "Volta Electrical", "https://www.voltaelectricians.com", "volta.png", "bellevue-wa"),
    "jacob": _client("jacob", "Jacob Electric", "", "jacob.png", "bellevue-wa"),
}


def validate(client: Client) -> Client:
    """Fail loudly on a client set up wrong rather than showing the wrong product."""
    unregistered = [job_type for job_type in client.job_types if job_type not in REGISTRY]
    if unregistered:
        raise ValueError(f"Client {client.key!r} enables unregistered job types: {', '.join(unregistered)}")
    return client


def current_client() -> Client:
    """The client named by PERMIT_CLIENT (default demo). Sign-in picks the client per session."""
    key = os.environ.get("PERMIT_CLIENT") or DEFAULT_CLIENT
    client = CLIENTS.get(key)
    if client is None:
        raise ValueError(f"Unknown PERMIT_CLIENT {key!r}. Known clients: {', '.join(sorted(CLIENTS))}")
    return validate(client)

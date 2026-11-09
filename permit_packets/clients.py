"""Who a deployment is set up for, and which job types they bought."""
from __future__ import annotations

import os
from dataclasses import dataclass

from permit_packets.job_types import REGISTRY

DEFAULT_CLIENT = "demo"


@dataclass(frozen=True)
class Client:
    key: str
    company_name: str
    job_types: tuple[str, ...]


CLIENTS: dict[str, Client] = {
    "demo": Client("demo", "", ("ev_charger",)),
}


def current_client() -> Client:
    """The client named by PERMIT_CLIENT. A typo fails loudly rather than showing the wrong product."""
    key = os.environ.get("PERMIT_CLIENT") or DEFAULT_CLIENT
    client = CLIENTS.get(key)
    if client is None:
        raise ValueError(f"Unknown PERMIT_CLIENT {key!r}. Known clients: {', '.join(sorted(CLIENTS))}")
    unregistered = [job_type for job_type in client.job_types if job_type not in REGISTRY]
    if unregistered:
        raise ValueError(f"Client {client.key!r} enables unregistered job types: {', '.join(unregistered)}")
    return client

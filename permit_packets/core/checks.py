"""One engineering check on a packet: what was checked, the result and whether it passed."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    result: str
    passed: bool

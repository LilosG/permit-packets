"""Checks a library panel against the job: the data sheet's bus, main and enclosure must fit what the
packet says is installed. A model that isn't in the library has no data to check, so no check is added."""
from __future__ import annotations

from permit_packets.core.checks import Check
from permit_packets.core.equipment import Equipment, find_equipment


def _problems_as_service(panel: Equipment, *, service_amps: int, bus_amps: int, meter_main: bool,
                         outdoors: bool) -> list[str]:
    problems = []
    if meter_main and not panel.meter_main:
        problems.append("it is a load center, not a meter-main")
    if not meter_main and panel.meter_main:
        problems.append("it is a meter-main, but the job has the meter separate")
    if panel.main != "breaker":
        problems.append("it has main lugs, so it can't be the service disconnect (230.70)")
    elif panel.main_amps != service_amps:
        problems.append(f"its main breaker is {panel.main_amps} A, not {service_amps} A")
    if panel.bus_amps < service_amps:
        problems.append(f"its bus is {panel.bus_amps} A, below the {service_amps} A service")
    if panel.bus_amps != bus_amps:
        problems.append(f"its bus is {panel.bus_amps} A, but the bus rating entered is {bus_amps} A")
    if outdoors and not panel.outdoor:
        problems.append("it is an indoor (NEMA 1) enclosure, but it goes outdoors")
    return problems


def service_panel_check(job) -> Check | None:
    """Service upgrade: the new service equipment against the service size, setup and location."""
    panel = find_equipment(job.panel_model, "panel")
    if panel is None or panel.bus_amps is None:
        return None
    meter_main = job.equipment == "meter_main"
    problems = _problems_as_service(panel, service_amps=job.new_service_amps, bus_amps=job.bus_amps,
                                    meter_main=meter_main, outdoors=meter_main or job.main_outdoors)
    if problems:
        return Check("Panel model", f"{panel.name}: {'; '.join(problems)}", False)
    return Check("Panel model", f"{panel.name}: {panel.bus_amps} A bus, {panel.main_amps} A main breaker, "
                                f"{'outdoor' if panel.outdoor else 'indoor'} enclosure, per the data sheet", True)


def subpanel_check(job) -> Check | None:
    """Subpanel: the panel against the feeder breaker and the rating the packet prints."""
    panel = find_equipment(job.subpanel_model, "panel")
    if panel is None or panel.bus_amps is None:
        return None
    problems = []
    if panel.meter_main:
        problems.append("it is a meter-main, not a subpanel")
    if panel.bus_amps != job.subpanel_amps:
        problems.append(f"its bus is {panel.bus_amps} A, but the subpanel rating entered is {job.subpanel_amps} A")
    if panel.bus_amps < job.feeder_breaker_amps:
        problems.append(f"its bus is {panel.bus_amps} A, below the {job.feeder_breaker_amps} A feeder breaker")
    if problems:
        return Check("Subpanel model", f"{panel.name}: {'; '.join(problems)}", False)
    main = f"{panel.main_amps} A main breaker" if panel.main == "breaker" else "main lugs"
    return Check("Subpanel model", f"{panel.name}: {panel.bus_amps} A bus, {main}, per the data sheet", True)

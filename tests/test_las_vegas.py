"""City of Las Vegas: what its checklists say and where they come from."""
from __future__ import annotations

import pytest

from permit_packets.jurisdictions import KNOWN, jurisdiction_for

LAS_VEGAS = KNOWN[("las vegas", "NV")]
JOB_TYPES = ("ev_charger", "service_upgrade", "subpanel", "appliance_circuit")


def test_las_vegas_is_a_known_city_that_takes_one_combined_pdf():
    assert jurisdiction_for("Las Vegas", "NV") is LAS_VEGAS
    assert LAS_VEGAS.known and LAS_VEGAS.single_pdf_only
    assert LAS_VEGAS.utility_short == "NV Energy"
    assert "2023 NEC" in LAS_VEGAS.code_note


@pytest.mark.parametrize("job_type", JOB_TYPES)
def test_every_checklist_cites_the_citys_own_documents(job_type):
    checklist = LAS_VEGAS.checklists[job_type]
    assert checklist.source_url.startswith("https://files.lasvegasnevada.gov/")
    assert all(note.text for note in checklist.notes)
    assert any("publishes no" in note.text for note in checklist.notes)
    assert any("one PDF per discipline" in note.text for note in checklist.notes)


def test_service_change_needs_no_plans_but_the_other_jobs_do():
    notes = lambda job: " ".join(n.text for n in LAS_VEGAS.checklists[job].notes)
    assert "without plans" in notes("service_upgrade")
    for job in ("ev_charger", "subpanel", "appliance_circuit"):
        assert "Any other work needs plans" in notes(job)

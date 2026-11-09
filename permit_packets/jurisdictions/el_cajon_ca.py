"""El Cajon, CA: from the city's published checklists."""
from __future__ import annotations

from permit_packets.jurisdictions import Checklist, Jurisdiction, Note, Requirement

EV_CHARGER = "ev_charger"

EL_CAJON = Jurisdiction(
    key="el-cajon-ca", name="El Cajon", state="CA", known=True,
    code_name="CEC",
    department="Community Development, Building Safety",
    phone="(619) 441-1726",
    website="https://elcajon.gov/your-government/departments/community-development/building-fire-safety-division/building-permits",
    website_label="El Cajon building permits",
    submit_how="The city's checklist doesn't say how to submit. Call Building Safety to confirm.",
    needs_parcel_number=True,
    checklists={
        EV_CHARGER: Checklist(
            items=(
                Requirement("Permit application with address, parcel number, owner, contractor and license", "application"),
                Requirement("Charger model number, manufacturer specifications and installation guidelines", "equipment"),
                Requirement("Plug-In Electric Vehicle Load Calculator, with the charger at 100%", "load"),
                Requirement("Fully dimensioned site plan, drawn to scale, showing structures, the panel and the charger", "site_plan"),
                Requirement("Electrical plan with single-line diagram, conduit and conductor sizes", "one_line"),
                Requirement("NRTL listing mark on the charging equipment", "equipment"),
                Requirement("Mechanical plan, if indoor ventilation applies", "ventilation"),
            ),
            source_url="https://elcajon.gov/home/showpublisheddocument/26307/637914284204530000",
            code_note="The city's checklist cites the 2019 California Electrical Code. Confirm the edition in force.",
            notes=(
                Note("disconnect", "El Cajon wants the disconnect readily accessible, in line of sight and within 50 ft of the charger."),
                Note("trench", "El Cajon wants trenching detailed on the plans, with 18 in minimum cover for direct burial."),
                Note("always", "Move the load figures onto El Cajon's own load calculator worksheet."),
            ),
        ),
    },
)

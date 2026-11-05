# Permit Packets

Turns a job address and one short form into a draft permit packet for a licensed electrician to review.

- `permit_packets/property_lookup.py` goes from an address to the city, building outlines, lot lines and an aerial.
- `permit_packets/property_plan.py` and `site_plan.py` draw the job to scale on that property.
- `permit_packets/jurisdictions.py` holds each city's rules, taken from its published checklist. A city not listed gets the general checklist and says so.
- `permit_packets/circuits.py` and `load_calculation.py` hold the code rules any electrical permit uses.
- `permit_packets/ev_charger.py` and `ev_packet_pdf.py` are the first permit type, built on those.
- `app.py` is the private demo, behind a sign-in.

Every packet is marked as a demo. Results are drafts and need review before anyone relies on them.

## Map data

| Data | Source | Terms |
|---|---|---|
| Address suggestions while typing | Photon, built on OpenStreetMap | Free with fair use, credit shown, no uptime promise |
| Address and city | US Census geocoder | Free public service |
| Building outlines | FEMA/ORNL USA Structures | Public data |
| Aerial | USGS National Map, NAIP Plus | Public domain, credit requested |
| Lot lines | County GIS, set in `COUNTY_PARCELS` | Check each county's terms before a paid build |
| Sharper, faster aerial (optional) | Mapbox satellite, when `MAPBOX_TOKEN` is set | Attribution required |

Don't use Google imagery here. Its terms bar exporting or tracing Maps content, and commercial use of satellite imagery is restricted.

## Run it

```
pip install -r requirements-dev.txt
pytest -q tests
DEMO_PASSWORD=choose-one uvicorn app:app --reload
```

Sign in with `DEMO_PASSWORD`. It deploys to Vercel on every push to `main`, with `DEMO_PASSWORD` set as a production environment variable.

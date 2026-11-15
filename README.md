# Permit Packets

Turns a job address and one short form into a draft permit packet for a licensed electrician to review.

## Layout

```
app.py                         The private demo: sign-in, generic job routes, the page
permit_packets/
  clients.py                   Each client: company, logo, cities, job types, optional sheet/PDF overrides
  core/                        The shared engine
    circuits.py                Code rules any electrical permit uses (wire, breaker, conduit)
    conductors.py              Service conductors, grounding electrode conductors, service conduit, solar 120% rule, feeders to a subpanel, branch circuits to a 240 V appliance
    load_calculation.py        Optional dwelling load calculation
    property_lookup.py         Address to city, building outlines, lot lines and an aerial
    property_plan.py           A property to scale, with named markers and an optional route
    site_plan.py               The to-scale site plan page, drawn from a list of markers
    pdf_base.py                Page look, build_document, cover_page (with the city stamp box), review_page, application_page, load_page, diagram fitting
    layout.py                  Letter (8.5x11 portrait) and tabloid (11x17 landscape) sheet geometry
    title_block.py             The title block on every packet page: address, parcel, sheet E-n, contractor, designer sign-off
    panel_data.py              Fault current / AIC check, existing GEC check (Table 250.66), panel details for the one-line
    heat.py                    NEC 310.15(B)(1) temperature correction for outdoor runs
    job_inputs.py              Sample-mode address, request plan to PropertyPlan
    preview.py                 Page images, one-file-per-document ZIP
    panel_schedule.py          Panel schedule: entered circuits only, a blank field-verify grid otherwise
    checks.py                  Check: one engineering check on a packet
    schemas.py                 Request models every job type shares
  jurisdictions/               What each city asks for, one checklist per job type
    general.py                 GENERAL_CHECKLISTS, the fallback for any job type
    oro_valley_az.py, el_cajon_ca.py
  job_types/
    __init__.py                Marker, Document, JobType, PacketResult, REGISTRY
    ev_charger/                EV charger: calc, pdf, schema, api
    service_upgrade/           Panel / service upgrade: calc, pdf, schema, api
    subpanel/                  Subpanel / feeder: calc, pdf, schema, api
    appliance_circuit/         240 V circuit (hot tub, sauna, heat pump, mini-split, other): calc, pdf, schema, api
  static/
    index.html                 The page shell
    assets/css/app.css
    assets/js/app.js           The core flow; knows nothing about any one permit
    assets/js/job-types/       One script per job type
tests/
  golden/                      Request payloads and the packets they must produce
```

A city not in `jurisdictions/` gets the general checklist and says so. So does a known city that has no checklist for the job type.

Job types so far: `ev_charger`, `service_upgrade`, `subpanel` and `appliance_circuit`. City service-upgrade, subpanel and 240 V circuit checklists are added per client during setup, so Oro Valley and El Cajon use the general ones for now.

Every packet is marked as a demo. Results are drafts and need review before anyone relies on them.

## Map data

| Data | Source | Terms |
|---|---|---|
| Address suggestions while typing | Mapbox Geocoding when `MAPBOX_TOKEN` is set (one line per street address and city); Photon, built on OpenStreetMap, only when there is no token | Mapbox: attribution required. Photon: free with fair use, no uptime promise |
| Address and city | US Census geocoder | Free public service |
| Building outlines | FEMA/ORNL USA Structures; in San Francisco the city's own surveyed Building Footprints (DataSF, `data.sf.gov`), because USA Structures has no outline for many San Francisco lots | Public data |
| Aerial | A local orthophoto where one is set up in `LOCAL_AERIALS` (Nashville Metro, NC OneMap for Mecklenburg, Maricopa County Assessor, San Diego County), else USGS National Map NAIP Plus | Public domain, credit requested |
| Lot lines | County GIS, set in `COUNTIES` (Pima, San Diego, Clark, Maricopa, Pinal and others) | Check each county's terms before a paid build |
| Lot lines, Pinal County | Arizona Department of Water Resources statewide parcel service, Pinal layer (`azwatermaps.azwater.gov`, built from county parcel data). Pinal County's own GIS host (`gismaps.pinalcountyaz.gov`) did not resolve when checked | Public service; the layer's description states no license or terms. Only parcel and address fields are read, never owner fields. Confirm terms with ADWR before a paid build |
| Sharper aerial (optional) | Mapbox satellite, when `MAPBOX_TOKEN` is set. Fetched as raster tiles at @2x, at the zoom that fills the plan at 1400 px (up to z20, Mapbox's z21 detail, 0.06 m per pixel), stitched and cropped to the plan box. It replaces USGS, and any local orthophoto coarser than 0.3 m, wherever it is sharper. Local orthophotos at 0.3 m or finer stay first | Attribution required |

### Keeping the picture, lot lines and buildings aligned

Every layer is drawn through one function, `PlanView`, in web mercator. The counties publish parcels in their own coordinate systems (San Francisco WGS84; Nashville, Mecklenburg, Clark, Pima and San Diego state plane feet; Maricopa web mercator; Pinal UTM), and each is asked for in latitude and longitude, which the county server converts (within about 4 ft of an exact transform). What differs between sources is where each is registered. `tools/measure_alignment.py` measures that in feet; the results that are large enough to correct are in `AERIAL_SHIFT_FT` and `FOOTPRINT_SHIFT_FT`. `tests/test_property_alignment.py` replays one real residential parcel per county and fails if the house sticks out of the lot, or past the front lot line, by more than 3 ft.

Aerials are asked for as lossless PNG (`png24`; plain `png` is 8-bit palette on MapServer exports), levelled and sharpened at the source's own resolution, resized once to 1400 px and JPEG-encoded once at quality 90 with full chroma. The review screen gets page images and the PDF from two requests (`/api/jobs/{slug}/packet` and `/api/jobs/{slug}/pdf`) so neither passes Vercel's 4.5 MB response limit; `tests/test_response_size.py` guards it.

Don't use Google imagery here. Its terms bar exporting or tracing Maps content, and commercial use of satellite imagery is restricted.

## Run it

```
pip install -r requirements-dev.txt
pytest -q tests
DEMO_PASSWORD=choose-one uvicorn app:app --reload
```

One deployment serves every client. Each signs in with their own password, set in `CLIENT_PASSWORDS` as JSON (`{"erke": "...", "elc": "..."}`); `DEMO_PASSWORD` still signs in the demo client. The session carries the client key, and that client's cities, logo and job types are all they see. A packet or property lookup for a city outside their list is a 403. Client logins print no demo banner or watermark; the demo login keeps both. The dashboard is browser-stored (localStorage) and labeled as a preview. It deploys to Vercel on every push to `main`, with `CLIENT_PASSWORDS` and `DEMO_PASSWORD` set as production environment variables.

## City settings

`Jurisdiction` fields beyond the checklist: `sheet_size` (letter or tabloid default; the request's `sheet_size` overrides it), `stamp_box_in` (empty stamp square on the cover), `title_sheet_blank_area_in` (an empty agency-stamp area: beside the stamp box when it fits, else a blank last sheet), `single_pdf_only` (no split-file ZIP), `design_ambient_f` and `design_ambient_source` (ASHRAE 2% design temperature for outdoor conductor derating). Cities with no checklist get the general checklist plus `STATE_AMENDMENTS`. `tests/test_city_compliance.py` builds a complete packet for every city and job type and fails if anything is not Ready, so a new requirement must be taught to the packet.

## Golden packets

`tests/golden/cases` holds request payloads and `tests/golden/snapshots` holds the packets the app made for them: the response JSON, the page count, each page's text and the ZIP file names. `tests/test_ev_golden.py` replays every case, so a refactor can't change a packet unnoticed. A deliberate change to a packet means regenerating the snapshots (`DEMO_PASSWORD=snap PYTHONPATH=. python tests/golden/make_snapshots.py`), and the diff shows exactly what changed. `to_current_request` in that test maps the stored payloads to whatever the routes take today.

## Adding a job type

A job type is one `JobType` value plus the code behind it. Use `job_types/ev_charger/`, `job_types/service_upgrade/` or `job_types/subpanel/` as the model.

1. **Create `job_types/<type>/`.**
   - `calc.py`: the job as a frozen dataclass, the checks and the flags. Put code rules every electrical permit needs in `core/` instead.
   - `pdf.py`: the pages. Build the cover and the review page with `core.pdf_base.cover_page` and `review_page`, and join the sections with `build_document`. Use `core.site_plan.AerialSitePlan` with a list of `PlanMarker`s for the site plan.
   - `schema.py`: `<Type>Request`, built on `core.schemas.JobRequestBase` (customer, address, contractor, license, sample mode, city, state, jurisdiction key and the plan). Check that the plan has the markers the type needs.
   - `api.py`: `build_response(request) -> PacketResult(pdf, body)`. The body carries what the page shows: `ready`, `checks`, `flags`, `jurisdiction` (from `jurisdiction_json(jurisdiction, job_type)`), `address`, `fields`, plus `job_type`, `documents`, `feature_page`, `summary` (label and value pairs), `build_steps` (the lines the page ticks through, with the real page count) and `submission_email` (subject and body). The route adds the page images and the PDF.
   - `__init__.py`: export `JOB_TYPE`.
2. **Fill in the `JobType`.**

   | Field | Meaning |
   |---|---|
   | `key`, `slug` | Stored name (`ev_charger`) and URL name (`ev-charger`) |
   | `label`, `short_label`, `blurb`, `icon` | The card on the job-type step, and "<short_label> permit packets" in the header. Draw a new `icon` in `ICONS` in `app.js` |
   | `markers` | `Marker(key, label, letter, color, prompt)` for each spot the tech taps on the plan |
   | `route_between` | Two marker keys the route runs between, or `None` |
   | `uses_home_loads` | Shows the home-loads block and sends `home` |
   | `documents` | `Document(file_stem, title)` for each page: ZIP file names and preview titles. There must be one per page |
   | `feature_page` | Index of the page shown large in the preview |
   | `request_model`, `build_response` | The request model and the function above |
   | `zip_name` | File name of the "each document" download |

3. **Register it** in `job_types/__init__.py`: import its `JOB_TYPE` and add it to `REGISTRY`.
4. **Add its checklist.** Put one in `GENERAL_CHECKLISTS` in `jurisdictions/general.py`, and add `checklists["<key>"]` to each city that has been set up for it. A city without one falls back to the general checklist and shows as "not known" for that type.
5. **Build its Details form.** Wrap its fields in `<div data-job-type="<key>">` in `index.html`. Use `class="contents"` on the wrapper when the field sits in a grid. Home loads go inside `data-uses="home_loads"`.
6. **Write `static/assets/js/job-types/<slug>.js`** and add its `<script>` tag before `app.js`. It calls `window.PermitJobTypes.register(key, module)` with: `init(ctx)`, `jobFields(formData)` for the payload, `planFields(marks)` to turn the marks into `{markers, route}`, and optionally `onProperty()`, `onDetails()` and `onSample()`.
7. **Enable it** for the clients that bought it in `clients.py`. Nobody sees a type until their client lists it.
8. **Tests it needs.**
   - Unit tests for the calc, with worked numbers.
   - A sample request and an entry in `SAMPLE_CASES` in `tests/test_job_types.py`. EV's come from `tests/golden/cases` with snapshots; newer types keep a current-shape request in `tests/samples/` (not in the golden folder, which the EV golden test replays).
   - Page count: the PDF has as many pages as `documents`. `test_every_type_has_one_document_per_page` checks this.
   - A request with a bad value returns 422.

### Setting up a client

Add a `Client` to `CLIENTS` in `clients.py` (company, website, `logo` file in `static/assets/logos/`, `jurisdiction_keys` with the default city first, job types, optional `sheet_size` and `single_pdf_only` overrides that beat the city's), add its password to `CLIENT_PASSWORDS`, and add it to `tests/test_clients.py`.

A client's cities need a checklist for every job type they bought. Before enabling a type for a client, add that type's checklist to each of the client's cities. The page says "General checklist" for any city that doesn't have one yet.

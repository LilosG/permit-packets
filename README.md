# Permit Packets

Turns a job address and one short form into a draft permit packet for a licensed electrician to review.

## Layout

```
app.py                         The private demo: sign-in, generic job routes, the page
permit_packets/
  clients.py                   Which job types a deployment sells (PERMIT_CLIENT, default "demo")
  core/                        The shared engine
    circuits.py                Code rules any electrical permit uses (wire, breaker, conduit)
    conductors.py              Service conductors, grounding electrode conductors, service conduit, solar 120% rule
    load_calculation.py        Optional dwelling load calculation
    property_lookup.py         Address to city, building outlines, lot lines and an aerial
    property_plan.py           A property to scale, with named markers and an optional route
    site_plan.py               The to-scale site plan page, drawn from a list of markers
    pdf_base.py                Page look, build_document, cover_page, review_page, application_page, load_page
    job_inputs.py              Sample-mode address, request plan to PropertyPlan
    preview.py                 Page images, one-file-per-document ZIP
    schemas.py                 Request models every job type shares
  jurisdictions/               What each city asks for, one checklist per job type
    general.py                 GENERAL_CHECKLISTS, the fallback for any job type
    oro_valley_az.py, el_cajon_ca.py
  job_types/
    __init__.py                Marker, Document, JobType, PacketResult, REGISTRY
    ev_charger/                EV charger: calc, pdf, schema, api
    service_upgrade/           Panel / service upgrade: calc, pdf, schema, api
  static/
    index.html                 The page shell
    assets/css/app.css
    assets/js/app.js           The core flow; knows nothing about any one permit
    assets/js/job-types/       One script per job type
tests/
  golden/                      Request payloads and the packets they must produce
```

A city not in `jurisdictions/` gets the general checklist and says so. So does a known city that has no checklist for the job type.

Job types so far: `ev_charger` and `service_upgrade`. City service-upgrade checklists are added per client during setup, so Oro Valley and El Cajon use the general one for now.

Every packet is marked as a demo. Results are drafts and need review before anyone relies on them.

## Map data

| Data | Source | Terms |
|---|---|---|
| Address suggestions while typing | Photon, built on OpenStreetMap | Free with fair use, credit shown, no uptime promise |
| Address and city | US Census geocoder | Free public service |
| Building outlines | FEMA/ORNL USA Structures | Public data |
| Aerial | USGS National Map, NAIP Plus | Public domain, credit requested |
| Lot lines | County GIS, set in `COUNTIES` (Pima, San Diego, Clark) | Check each county's terms before a paid build |
| Sharper, faster aerial (optional) | Mapbox satellite, when `MAPBOX_TOKEN` is set | Attribution required |

Don't use Google imagery here. Its terms bar exporting or tracing Maps content, and commercial use of satellite imagery is restricted.

## Run it

```
pip install -r requirements-dev.txt
pytest -q tests
DEMO_PASSWORD=choose-one uvicorn app:app --reload
```

Sign in with `DEMO_PASSWORD`. `PERMIT_CLIENT` picks which client's job types are on (default `demo`); an unknown name fails at the first request. It deploys to Vercel on every push to `main`, with `DEMO_PASSWORD` set as a production environment variable.

## Golden packets

`tests/golden/cases` holds request payloads and `tests/golden/snapshots` holds the packets the app made for them: the response JSON, the page count, each page's text and the ZIP file names. `tests/test_ev_golden.py` replays every case, so a refactor can't change a packet unnoticed. A deliberate change to a packet means regenerating the snapshots, and the diff shows exactly what changed. `to_current_request` in that test maps the stored payloads to whatever the routes take today.

## Adding a job type

A job type is one `JobType` value plus the code behind it. Use `job_types/ev_charger/` or `job_types/service_upgrade/` as the model.

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

A client's cities need a checklist for every job type they bought. Before enabling a type for a client, add that type's checklist to each of the client's cities. The page says "General checklist" for any city that doesn't have one yet.

# Permit Packets

Turns one electrical job into a draft permit packet for a licensed electrician to review.

- `permit_packets/circuits.py` and `load_calculation.py` hold the code rules any electrical permit uses.
- `permit_packets/ev_charger.py` and `ev_packet_pdf.py` are the first permit type, built on those.
- `permit_packets/web.py` is the private demo, behind a login.

Every packet is marked as a demo and uses the Town of Oro Valley's checklist. Results are drafts and need review before anyone relies on them.

## Run it

```
pip install -r requirements-dev.txt
pytest -q tests
DEMO_PASSWORD=choose-one uvicorn permit_packets.web:app --reload
```

Log in as `mike` with `DEMO_PASSWORD`. It deploys to Vercel from `api/index.py`, with `DEMO_PASSWORD` set as a production environment variable.

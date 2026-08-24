
# Freight Calculator V3 — Prototype

This version focuses on demonstrating the client's intended workflow quickly and clearly.

## Run

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## V3 improvements

- Chargeable weight is automatically MAX(actual, volumetric).
- No "Consol Count" clutter on the main form.
- EXW is described as "EXW / Door Pickup".
- Standard origin charges are separated from additional services.
- Conditional service inputs appear inside the service's own expander.
- Quarantine immediately exposes attendance minutes.
- Labelling exposes flat/per-piece basis and quantity.
- Palletise, shrink wrap, storage, cartage, photos and connote options expose their quantities when selected.
- On Application / Request items are clearly separated from automatically rated charges.
- USD components are converted to a single AUD quotation using the user-entered FX rate.
- Multiple airline/routing options can be reviewed before selecting the quoted option.
- PDF quotation generation remains available.

## Prototype disclaimer

This is a proof of concept. Some tariff rows contain operational assumptions or "On Application / On Request" wording. Those are surfaced rather than silently invented. Final implementation should validate tariff interpretation and operational rules with the client.

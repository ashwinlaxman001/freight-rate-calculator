
import re
import math
import pandas as pd


def _money(value):
    return f"AUD {value:,.2f}"


def _usd(value):
    return f"USD {value:,.2f}"


def _extract_number(value):
    if value is None:
        return None
    text = str(value).replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(m.group()) if m else None


def calculate_chargeable_weight(actual_weight, volumetric_weight):
    return max(float(actual_weight), float(volumetric_weight or 0))


def _select_bracket(row, weight):
    # Source tariff has Standard, +45, +100 and +300.
    if weight <= 45:
        return "Standard", row["standard"]
    if weight <= 100:
        return "+45", row["plus45"]
    if weight <= 300:
        return "+100", row["plus100"]
    return "+300", row["plus300"]


def find_import_options(rates, origin, destination, chargeable_weight, airline_filter="All"):
    subset = rates[
        (rates["origin_code"].str.upper() == origin.upper()) &
        (rates["destination_code"].str.upper() == destination.upper())
    ].copy()

    if airline_filter != "All":
        subset = subset[subset["airline"].str.upper() == airline_filter.upper()].copy()

    rows = []
    for _, row in subset.iterrows():
        bracket, rate = _select_bracket(row, chargeable_weight)

        if pd.isna(rate):
            continue

        minimum = float(row["minimum_usd"] or 0)
        weight_freight = float(chargeable_weight) * float(rate)
        base_freight = max(weight_freight, minimum)

        rows.append({
            "airline": row["airline"],
            "routing": row["routing"],
            "bracket": bracket,
            "rate_per_kg": float(rate),
            "minimum_usd": minimum,
            "weight_freight_usd": weight_freight,
            "base_freight_usd": base_freight,
            "transit_days": row["transit_days"],
            "cut_off": row["cut_off"],
            "flight": row["flight"],
            "currency": row["currency"],
            "origin_charges_raw": row["origin_charges_raw"],
            "au_arrival_raw": row["au_arrival_raw"],
            "au_cto_raw": row["au_cto_raw"],
            "source_row": int(row["source_row"]),
            "source_file": row["source_file"],
        })

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values(["base_freight_usd", "airline", "routing"]).reset_index(drop=True)
    return result


def _max_min(weight, minimum, per_kg):
    return max(float(minimum), float(weight) * float(per_kg))


def calculate_origin_charges(
    row,
    chargeable_weight,
    include_documentation=True,
    include_labelling=True,
    include_screening=True,
    customs_clearance=False,
):
    items = []
    total = 0.0
    raw = row.get("origin_charges_raw", "")

    if include_documentation:
        amount = 40.0
        total += amount
        items.append({
            "name": "Documentation",
            "display": _usd(amount),
            "source": f"Import Tarrif.xlsx → INDIA → row {row['source_row']} (source text: documentation $40)",
        })

    if include_labelling:
        amount = max(10.0, chargeable_weight * 0.07)
        total += amount
        items.append({
            "name": "Labelling",
            "display": f"{_usd(amount)} — MAX(USD 10, {chargeable_weight:g} × 0.07)",
            "source": f"Import Tarrif.xlsx → INDIA → row {row['source_row']}",
        })

    if include_screening:
        amount = max(15.0, chargeable_weight * 0.15)
        total += amount
        items.append({
            "name": "Origin Screening",
            "display": f"{_usd(amount)} — MAX(USD 15, {chargeable_weight:g} × 0.15)",
            "source": f"Import Tarrif.xlsx → INDIA → row {row['source_row']}",
        })

    if customs_clearance:
        amount = 65.0
        total += amount
        items.append({
            "name": "Customs Clearance",
            "display": _usd(amount),
            "source": f"Import Tarrif.xlsx → INDIA → row {row['source_row']} (If Applicable)",
        })

    # CCX is present in the source as "3% Min $25", but its calculation base is
    # not specified in the supplied India tariff. We intentionally do not invent it.
    if "CCX" in raw.upper():
        items.append({
            "name": "CCX",
            "display": "Not auto-calculated — tariff says 3% / minimum USD 25, but calculation base is not specified",
            "source": f"Import Tarrif.xlsx → INDIA → row {row['source_row']}",
        })

    if "ON REQUEST" in raw.upper():
        items.append({
            "name": "INL / Collection / Customs Clearance",
            "display": "ON REQUEST — excluded from automatic total",
            "source": f"Import Tarrif.xlsx → INDIA → row {row['source_row']}",
        })

    return {"items": items, "total_usd": total}


def calculate_au_charges(
    rules,
    chargeable_weight,
    cargo_handling,
    service_type,
    mawb_count,
    hawb_count,
    consol_count,
    cto,
    dg,
    sac,
    tranship,
    late_reporting,
    manual_registration,
    quarantine,
    quarantine_minutes,
    palletise,
    shrink_wrap,
    pallet_count,
    labelling_au,
    label_pieces,
    label_basis,
    photos,
    third_party_connote,
    connote_count,
    cartage,
    fsc_aud,
    storage,
    storage_days,
    undeclared_dg,
    document_processing,
    xray_repack,
    skid_count,
    weekend_collection,
    buildup,
    handover_bond,
):
    items = []
    flags = []
    total = 0.0
    w = float(chargeable_weight)

    def add(name, amount, display, source):
        nonlocal total
        total += amount
        items.append({
            "name": name,
            "amount": amount,
            "display": display,
            "source": source,
        })

    # --- Import Fees ---
    if cargo_handling == "Breakbulk":
        r = rules["Breakbulk"]
        minimum = _extract_number(r["min_raw"]) or 0
        perkg = _extract_number(r["per_kg_raw"]) or 0
        amount = _max_min(w, minimum, perkg)
        add(
            "Breakbulk",
            amount,
            f"{_money(amount)} — MAX({minimum:g}, {w:g} × {perkg:g})",
            r["source"],
        )

    # Cargo Automation + Administration are under Break Bulk charges.
    if cargo_handling in ("Loose Cargo", "Breakbulk"):
        r = rules["Cargo Automation Fee"]
        amount = (_extract_number(r["min_raw"]) or 0) * hawb_count
        add("Cargo Automation Fee", amount, f"{_money(amount)} — {hawb_count} HAWB", r["source"])

        r = rules["Administration Fee"]
        amount = (_extract_number(r["min_raw"]) or 0) * mawb_count
        add("Administration Fee", amount, f"{_money(amount)} — {mawb_count} MAWB/Sub-MAWB", r["source"])

    if cargo_handling == "Unitised / BUP" and handover_bond:
        r = rules["Handover Fee"]
        minimum = _extract_number(r["min_raw"]) or 0
        perkg = _extract_number(r["per_kg_raw"]) or 0
        amount = _max_min(w, minimum, perkg)
        add("BUP Handover Fee", amount, f"{_money(amount)} — MAX({minimum:g}, {w:g} × {perkg:g})", r["source"])

    if cargo_handling == "Unitised / BUP":
        r = rules["Airline Terminal Fee (Unitised)"]
        minimum = _extract_number(r["min_raw"]) or 0
        perkg = _extract_number(r["per_kg_raw"]) or 0
        if cto == "Dnata":
            perkg += 0.02
        amount = _max_min(w, minimum, perkg)
        add("Airline Terminal Fee — Unitised", amount, f"{_money(amount)} — MAX({minimum:g}, {w:g} × {perkg:g})", r["source"])

        r = rules["Import Document Fee (AMI Co Load)"]
        amount = (_extract_number(r["min_raw"]) or 0) * consol_count
        add("Import Document Fee — AMI Co Load", amount, f"{_money(amount)} — {consol_count} consol", r["source"])

    else:
        r = rules["Airline Terminal Fee"]
        minimum = (_extract_number(r["min_raw"]) or 0) + (5 if cto == "Dnata" else 0)
        perkg = (_extract_number(r["per_kg_raw"]) or 0) + (0.05 if cto == "Dnata" else 0)
        amount = _max_min(w, minimum, perkg)
        add("Airline Terminal Fee", amount, f"{_money(amount)} — MAX({minimum:g}, {w:g} × {perkg:g})", r["source"])

        r = rules["Import Document Fee"]
        amount = ((_extract_number(r["min_raw"]) or 0) + (5 if cto == "Dnata" else 0)) * mawb_count
        add("Import Document Fee", amount, f"{_money(amount)} — {mawb_count} MAWB", r["source"])

    # ITF/IDF is explicitly under IMPORT EX WORKS.
    if service_type == "EXW":
        r = rules["International Terminal Fee (ITF/IDF)"]
        minimum = _extract_number(r["info"]) or 120
        perkg = _extract_number(r["min_raw"]) or 0.20
        amount = _max_min(w, minimum, perkg)
        add("International Terminal Fee (ITF/IDF)", amount, f"{_money(amount)} — MAX({minimum:g}, {w:g} × {perkg:g})", r["source"])

    # --- Conditional Import Surcharges ---
    if storage:
        r = rules["Storage"]
        daily = _extract_number(r["min_raw"]) or 54
        perkg = _extract_number(r["per_kg_raw"]) or 0.28
        amount_per_day = daily + (w * perkg)
        amount = amount_per_day * int(storage_days)
        add(
            "Storage",
            amount,
            f"{_money(amount)} — {storage_days} day(s) × ({daily:g} + {w:g} × {perkg:g})",
            r["source"],
        )

    if late_reporting:
        r = rules["Late Reporting Fee"]
        amount = (_extract_number(r["min_raw"]) or 58) * mawb_count
        add("Late Reporting Fee", amount, f"{_money(amount)} — {mawb_count} MAWB", r["source"])

    if manual_registration:
        r = rules["Manual Registration Fee"]
        amount = _extract_number(r["min_raw"]) or 28
        add("Manual Registration Fee", amount, f"{_money(amount)} — per registration", r["source"])

    if dg:
        r = rules["Dangerous Goods Transfer"]
        minimum = _extract_number(r["min_raw"]) or 30
        perkg = _extract_number(r["per_kg_raw"]) or 0.26
        amount = _max_min(w, minimum, perkg)
        add("Dangerous Goods Transfer", amount, f"{_money(amount)} — MAX({minimum:g}, {w:g} × {perkg:g})", r["source"])

    if sac:
        r = rules["Self-Assessed Clearance - SAC Entry"]
        amount = _extract_number(r["min_raw"]) or 46
        add("SAC Entry", amount, f"{_money(amount)} — per entry", r["source"])

    if tranship:
        r = rules["International Tranship Fee"]
        amount = (_extract_number(r["min_raw"]) or 51) * hawb_count
        add("International Transhipment", amount, f"{_money(amount)} — {hawb_count} HAWB", r["source"])

    if quarantine:
        r = rules["Quarantine Attendance & Facilitation Fee"]
        first = _extract_number(r["min_raw"]) or 160
        if quarantine_minutes <= 30:
            amount = first
        else:
            extra_hours = math.ceil((quarantine_minutes - 30) / 60)
            hourly = 86
            amount = first + extra_hours * hourly
        add(
            "Quarantine Attendance & Facilitation",
            amount,
            f"{_money(amount)} — {quarantine_minutes} min",
            r["source"],
        )

    if palletise:
        r = rules["Palletise Cargo"]
        amount = (_extract_number(r["min_raw"]) or 57) * pallet_count
        add("Palletise Cargo", amount, f"{_money(amount)} — {pallet_count} pallet(s)", r["source"])

    if shrink_wrap:
        r = rules["Shrink wrap"]
        amount = (_extract_number(r["min_raw"]) or 18) * pallet_count
        add("Shrink Wrap", amount, f"{_money(amount)} — {pallet_count} pallet(s)", r["source"])

    if labelling_au:
        r = rules["Labelling/Removing Labels from Cargo"]
        if label_basis == "Flat charge":
            amount = _extract_number(r["min_raw"]) or 29
            display = f"{_money(amount)} — flat charge"
        else:
            amount = 3.15 * label_pieces
            display = f"{_money(amount)} — {label_pieces} piece(s) × 3.15"
        add("AU Labelling / Remove Labels", amount, display, r["source"])

    if photos:
        r = rules["Photos / Check Weigh & Measure"]
        amount = (_extract_number(r["min_raw"]) or 30) * hawb_count
        add("Photos / Check Weigh & Measure", amount, f"{_money(amount)} — {hawb_count} HAWB", r["source"])

    if third_party_connote:
        r = rules["3rd Party Cartage Connote Completion"]
        amount = (_extract_number(r["min_raw"]) or 13) * connote_count
        add("3rd Party Cartage Connote Completion", amount, f"{_money(amount)} — {connote_count} connote(s)", r["source"])

    if weekend_collection:
        r = rules["Weekend Collection ex AMI"]
        flags.append("Weekend Collection is ON APPLICATION and is excluded from the automatic total.")
        items.append({
            "name": "Weekend Collection ex AMI",
            "amount": 0.0,
            "display": "ON APPLICATION — excluded from total",
            "source": r["source"],
        })

    if cartage:
        r = rules["Cartage*"]
        base = _extract_number(r["min_raw"]) or 85
        perkg = _extract_number(r["per_kg_raw"]) or 0.22
        amount = base + w * perkg + float(fsc_aud or 0)
        add(
            "Metro Cartage",
            amount,
            f"{_money(amount)} — {base:g} + ({w:g} × {perkg:g}) + FSC {float(fsc_aud or 0):g}",
            r["source"],
        )
        if not fsc_aud:
            flags.append("Cartage FSC amount was not supplied in the source tariff; calculated with FSC = AUD 0.00.")

    if undeclared_dg:
        # This is listed on the Screening sheet, not Import Surcharges.
        flags.append("Undeclared Dangerous Goods is on the AU Screening sheet; it is not included in this Import prototype total.")

    if document_processing:
        flags.append("Document Processing Fee is on the AU Screening sheet; not included in this Import prototype total.")

    if xray_repack:
        flags.append("X-Ray Repack is on the AU Screening sheet; not included in this Import prototype total.")

    if buildup:
        flags.append("Build Up is ON APPLICATION and excluded from the automatic total.")

    return {"items": items, "total_aud": total, "flags": flags}

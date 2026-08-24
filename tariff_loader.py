
from pathlib import Path
import re
import pandas as pd


def _clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).replace("\n", " ").replace("\t", " ").strip()


def _to_float(value):
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(",", "")
    if not text:
        return None

    # Remove common currency / text noise.
    text = text.replace("$", "").replace("AUD", "").replace("USD", "")
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(m.group()) if m else None


def load_import_rates(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="INDIA", header=0)

    out = pd.DataFrame()
    out["month"] = df["MONTH"].map(_clean_text)
    out["destination_code"] = df["DESTINATION"].map(_clean_text)
    out["origin"] = df["ORIGIN"].map(_clean_text)
    out["origin_code"] = df["ORIGIN CODE \n"].map(_clean_text).str.upper()
    out["cut_off"] = df["CUT OFF"].map(_clean_text)
    out["airline"] = df["AIRLINE"].map(_clean_text).str.upper()
    out["routing"] = df["ROUTING"].map(_clean_text)
    out["transit_days"] = pd.to_numeric(df["A2A TRANSIT ONLY "], errors="coerce")
    out["flight"] = df["FLIGHT"].map(_clean_text)
    out["currency"] = df["CURRENCY "].map(_clean_text).str.upper()

    out["minimum_usd"] = df["AIR FREIGHT \nMINIMUM\n"].map(_to_float)
    out["standard"] = df["AIRFREIGHT Standard PER KG"].map(_to_float)
    out["plus45"] = df["AIRFREIGHT .+45 PER KG"].map(_to_float)
    out["plus100"] = df["AIRFREIGHT\n.+100\nPER KG"].map(_to_float)
    out["plus300"] = df["AIRFREIGHT\n.+300\nPER KG"].map(_to_float)

    out["origin_charges_raw"] = df[
        "ORIGIN / EXW CHARGES  - CHARGES IN GBP \n* Based on CW  - subject to change*"
    ].map(_clean_text)

    out["au_arrival_raw"] = df[
        "AU ARRIVAL CHARGES - IN AUD\n* Based on CW  - subject to change*"
    ].map(_clean_text)

    out["au_cto_raw"] = df[" AU CTO"].map(_clean_text)
    out["source_file"] = path.name
    out["source_sheet"] = "INDIA"
    # Excel row number: header is row 1, first data row is row 2.
    out["source_row"] = range(2, len(out) + 2)

    out = out[
        out["origin_code"].ne("") &
        out["destination_code"].ne("") &
        out["airline"].ne("")
    ].copy()

    return out.reset_index(drop=True)


def _find_rule(df, description):
    normalized = df[0].fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip().str.casefold()
    target = re.sub(r"\s+", " ", description).strip().casefold()
    rows = df[normalized.eq(target)]
    if rows.empty:
        raise ValueError(f"Could not find AU tariff rule: {description}")
    return rows.iloc[0]


def load_au_rules(path: Path):
    fees = pd.read_excel(path, sheet_name="Page 1 - Import Fees", header=None)
    surcharges = pd.read_excel(path, sheet_name="Page 2 - Import Surcharges", header=None)

    rules = {}

    # Import Fees
    descriptions = [
        "Breakbulk",
        "Cargo Automation Fee",
        "Administration Fee",
        "Airline Terminal Fee",
        "Import Document Fee",
        "Handover Fee",
        "Airline Terminal Fee (Unitised)",
        "Import Document Fee (AMI Co Load)",
        "International Terminal Fee (ITF/IDF)",
    ]

    for desc in descriptions:
        row = _find_rule(fees, desc)
        rules[desc] = {
            "description": desc,
            "info": "" if pd.isna(row[1]) else str(row[1]),
            "min_raw": "" if pd.isna(row[2]) else str(row[2]),
            "per_kg_raw": "" if pd.isna(row[3]) else str(row[3]),
            "charge_type": "" if pd.isna(row[4]) else str(row[4]),
            "source": f"AU_National_Tariffs.xlsx → Page 1 - Import Fees → row {row.name + 1}",
        }

    # Import Surcharges
    descriptions2 = [
        "Storage",
        "Late Reporting Fee",
        "Manual Registration Fee",
        "Dangerous Goods Transfer",
        "Self-Assessed Clearance - SAC Entry",
        "International Tranship Fee",
        "Quarantine Attendance & Facilitation Fee",
        "Palletise Cargo",
        "Shrink wrap",
        "Labelling/Removing Labels from Cargo",
        "Photos / Check Weigh & Measure",
        "3rd Party Cartage Connote Completion",
        "Weekend Collection ex AMI",
        "Cartage*",
    ]

    for desc in descriptions2:
        row = _find_rule(surcharges, desc)
        rules[desc] = {
            "description": desc,
            "info": "" if pd.isna(row[1]) else str(row[1]),
            "min_raw": "" if pd.isna(row[2]) else str(row[2]),
            "per_kg_raw": "" if pd.isna(row[3]) else str(row[3]),
            "charge_type": "" if pd.isna(row[4]) else str(row[4]),
            "source": f"AU_National_Tariffs.xlsx → Page 2 - Import Surcharges → row {row.name + 1}",
        }

    # Values in the workbook are current tariff data; parser extracts numbers from the source cells.
    return rules

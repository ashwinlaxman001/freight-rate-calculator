
import pandas as pd
import streamlit as st
from pathlib import Path

from tariff_loader import load_import_rates, load_au_rules
from rating_engine import (
    calculate_chargeable_weight,
    find_import_options,
    calculate_origin_charges,
    calculate_au_charges,
)
from quote_pdf import build_quote_pdf

BASE_DIR = Path(__file__).resolve().parent
IMPORT_FILE = BASE_DIR / "data" / "Import Tarrif.xlsx"
AU_FILE = BASE_DIR / "data" / "AU_National_Tariffs.xlsx"

st.set_page_config(page_title="Freight Quotation Calculator", page_icon="✈️", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
.section-card {
    padding: 1rem 1.1rem;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    margin-bottom: 1rem;
}
.total-box {
    padding: 1rem 1.2rem;
    border-radius: 12px;
    background: #f3f4f6;
}
</style>
""", unsafe_allow_html=True)

st.title("✈️ Freight Rate Calculator")
st.caption("India → Australia Import | Prototype Rating Engine")

@st.cache_data(show_spinner=False)
def load_data():
    return load_import_rates(IMPORT_FILE), load_au_rules(AU_FILE)

rates, au_rules = load_data()

if "shipments" not in st.session_state:
    st.session_state.shipments = []

# ---------- SHIPMENT DETAILS ----------
st.header("1. Shipment Details")

origins = sorted(rates.origin_code.dropna().unique())
destinations = sorted(rates.destination_code.dropna().unique())
airlines = sorted(rates.airline.dropna().unique())

with st.container(border=True):
    c1, c2, c3 = st.columns(3)
    with c1:
        origin = st.selectbox("Origin Airport", origins, index=origins.index("BOM") if "BOM" in origins else 0)
        actual_weight = st.number_input("Actual Weight (kg)", min_value=0.01, value=50.0, step=0.5)
    with c2:
        destination = st.selectbox("Destination Airport", destinations, index=destinations.index("BNE") if "BNE" in destinations else 0)
        volumetric_weight = st.number_input("Volumetric Weight (kg)", min_value=0.0, value=0.0, step=0.5)
    with c3:
        chargeable_weight = calculate_chargeable_weight(actual_weight, volumetric_weight)
        st.metric("Chargeable Weight", f"{chargeable_weight:,.2f} kg")
        service_type = st.radio(
            "Service Type",
            ["Airport-to-Airport", "EXW / Door Pickup"],
            horizontal=True,
            help="EXW activates EXW-related AU/import handling logic.",
        )

    c4, c5, c6 = st.columns(3)
    with c4:
        cargo_handling = st.selectbox("Cargo Handling", ["Loose Cargo", "Unitised / BUP", "Breakbulk"])
    with c5:
        airline_filter = st.selectbox("Airline / Carrier", ["All"] + airlines)
    with c6:
        cto = st.selectbox("Australian CTO", ["Standard", "Dnata"])

    c7, c8 = st.columns(2)
    with c7:
        mawb_count = st.number_input("MAWB Count", min_value=1, value=1, step=1)
    with c8:
        hawb_count = st.number_input("HAWB Count", min_value=1, value=1, step=1)

# ---------- STANDARD CHARGES ----------
st.header("2. Standard Charges")

with st.container(border=True):
    st.info("Standard tariff-driven charges are calculated automatically. Additional services are selected below.")

    s1, s2, s3 = st.columns(3)
    with s1:
        include_documentation = st.checkbox("Origin Documentation", value=True)
    with s2:
        include_labelling = st.checkbox("Origin Labelling", value=True)
    with s3:
        include_origin_screening = st.checkbox("Origin Screening", value=True)

# ---------- OPTIONAL SERVICES ----------
st.header("3. Additional / Conditional Services")
st.caption("Select a service only when it applies. The required quantity/time input appears immediately.")

with st.container(border=True):
    # Each expander contains its own conditional inputs.
    with st.expander("☣️ Dangerous Goods", expanded=False):
        dg = st.checkbox("Apply Dangerous Goods Transfer", key="dg")
        st.caption("Tariff-driven: minimum + per kg.")

    with st.expander("🧾 SAC Entry", expanded=False):
        sac = st.checkbox("Apply SAC Entry", key="sac")

    with st.expander("🔁 International Transhipment", expanded=False):
        tranship = st.checkbox("Apply International Transhipment", key="tranship")
        tranship_hawb_count = st.number_input(
            "Transhipment HAWBs", min_value=1, value=int(hawb_count), step=1,
            disabled=not tranship, key="tranship_hawb"
        )

    with st.expander("🛂 Quarantine Attendance", expanded=False):
        quarantine = st.checkbox("Apply Quarantine Attendance", key="quarantine")
        quarantine_minutes = st.number_input(
            "Attendance time (minutes)", min_value=1, value=30, step=5,
            disabled=not quarantine, key="quarantine_minutes"
        )

    with st.expander("🪵 Palletise Cargo", expanded=False):
        palletise = st.checkbox("Apply Palletise Cargo", key="palletise")
        pallet_count = st.number_input(
            "Number of pallets", min_value=1, value=1, step=1,
            disabled=not palletise, key="pallet_count"
        )

    with st.expander("📦 Shrink Wrap", expanded=False):
        shrink_wrap = st.checkbox("Apply Shrink Wrap", key="shrink_wrap")
        shrink_pallet_count = st.number_input(
            "Pallets to shrink wrap", min_value=1, value=1, step=1,
            disabled=not shrink_wrap, key="shrink_pallet_count"
        )

    with st.expander("🏷️ AU Labelling / Removing Labels", expanded=False):
        labelling_au = st.checkbox("Apply AU Labelling", key="labelling_au")
        label_basis = st.radio(
            "Charge basis", ["Flat charge", "Per piece"],
            horizontal=True, disabled=not labelling_au, key="label_basis"
        )
        label_pieces = st.number_input(
            "Number of pieces", min_value=1, value=1, step=1,
            disabled=(not labelling_au or label_basis != "Per piece"),
            key="label_pieces"
        )

    with st.expander("📷 Photos / Check Weigh & Measure", expanded=False):
        photos = st.checkbox("Apply Photos / Check Weigh & Measure", key="photos")
        photo_hawb_count = st.number_input(
            "HAWBs", min_value=1, value=int(hawb_count), step=1,
            disabled=not photos, key="photo_hawb_count"
        )

    with st.expander("📝 3rd Party Cartage Connote", expanded=False):
        third_party_connote = st.checkbox("Apply Connote Completion", key="third_party_connote")
        connote_count = st.number_input(
            "Number of connotes", min_value=1, value=1, step=1,
            disabled=not third_party_connote, key="connote_count"
        )

    with st.expander("🚚 Metro Cartage", expanded=False):
        cartage = st.checkbox("Apply Cartage", key="cartage")
        fsc_aud = st.number_input(
            "FSC amount (AUD)", min_value=0.0, value=0.0, step=1.0,
            disabled=not cartage, key="fsc_aud",
            help="The tariff references FSC but does not give a fixed FSC amount; enter the applicable FSC here."
        )

    with st.expander("🏢 Storage", expanded=False):
        storage = st.checkbox("Apply Storage", key="storage")
        storage_days = st.number_input(
            "Chargeable storage days", min_value=1, value=1, step=1,
            disabled=not storage, key="storage_days"
        )

    with st.expander("⚠️ Late Reporting / Manual Registration", expanded=False):
        late_reporting = st.checkbox("Late Reporting Fee", key="late_reporting")
        manual_registration = st.checkbox("Manual Registration Fee", key="manual_registration")

# ---------- ON APPLICATION ----------
st.header("4. On Application / Request")
with st.container(border=True):
    o1, o2, o3, o4 = st.columns(4)
    with o1:
        weekend_collection = st.checkbox("Weekend Collection")
    with o2:
        buildup = st.checkbox("Build Up")
    with o3:
        handover_bond = st.checkbox(
            "BUP Handover Under Bond",
            disabled=(cargo_handling != "Unitised / BUP")
        )
    with o4:
        customs_clearance = st.checkbox("Origin Customs Clearance")

    if any([weekend_collection, buildup]):
        st.warning("Selected On Application items will be displayed but excluded from the automatic total.")

# ---------- QUOTATION SETTINGS ----------
st.header("5. Quotation")

exchange_rate = st.number_input(
    "USD → AUD Exchange Rate (1 USD = AUD)",
    min_value=0.0001, value=1.55, step=0.01, format="%.4f",
)

if st.button("➕ Add Shipment to Quote", type="primary", use_container_width=True):
    shipment = {
        "origin": origin, "destination": destination,
        "actual_weight": actual_weight, "volumetric_weight": volumetric_weight,
        "chargeable_weight": chargeable_weight,
        "service_type": service_type, "cargo_handling": cargo_handling,
        "airline_filter": airline_filter, "cto": cto,
        "mawb_count": int(mawb_count), "hawb_count": int(hawb_count),
        "include_documentation": include_documentation,
        "include_labelling": include_labelling,
        "include_origin_screening": include_origin_screening,
        "customs_clearance": customs_clearance,
        "dg": dg, "sac": sac, "tranship": tranship,
        "tranship_hawb_count": int(tranship_hawb_count),
        "quarantine": quarantine, "quarantine_minutes": int(quarantine_minutes),
        "palletise": palletise, "pallet_count": int(pallet_count),
        "shrink_wrap": shrink_wrap, "shrink_pallet_count": int(shrink_pallet_count),
        "labelling_au": labelling_au, "label_pieces": int(label_pieces),
        "label_basis": label_basis,
        "photos": photos, "photo_hawb_count": int(photo_hawb_count),
        "third_party_connote": third_party_connote, "connote_count": int(connote_count),
        "cartage": cartage, "fsc_aud": float(fsc_aud),
        "storage": storage, "storage_days": int(storage_days),
        "late_reporting": late_reporting,
        "manual_registration": manual_registration,
        "weekend_collection": weekend_collection, "buildup": buildup,
        "handover_bond": handover_bond,
        "exchange_rate": exchange_rate,
    }
    st.session_state.shipments.append(shipment)
    st.success("Shipment added to quotation.")
    st.rerun()

# ---------- RESULTS ----------
if st.session_state.shipments:
    st.divider()
    st.header("6. Quote Breakdown")

    all_quote_rows = []

    for idx, shipment in enumerate(st.session_state.shipments, 1):
        st.subheader(
            f"Shipment {idx}  |  {shipment['origin']} → {shipment['destination']}  |  "
            f"{shipment['chargeable_weight']:,.2f} kg"
        )

        options = find_import_options(
            rates, shipment["origin"], shipment["destination"],
            shipment["chargeable_weight"], shipment["airline_filter"]
        )

        if options.empty:
            st.error("No matching tariff options found for this route/weight.")
            continue

        # Show ALL valid airline options and let operator choose one.
        labels = [
            f"{r.airline} | {r.routing} | {r.bracket} | "
            f"USD {r.rate_per_kg:,.4f}/kg | Freight USD {r.base_freight_usd:,.2f}"
            for r in options.itertuples()
        ]

        selected_pos = st.selectbox(
            "Select airline / routing",
            range(len(labels)),
            index=0,
            format_func=lambda x: labels[x],
            key=f"airline_select_{idx}",
        )
        selected = options.iloc[selected_pos].to_dict()

        origin_result = calculate_origin_charges(
            row=selected,
            chargeable_weight=shipment["chargeable_weight"],
            include_documentation=shipment["include_documentation"],
            include_labelling=shipment["include_labelling"],
            include_screening=shipment["include_origin_screening"],
            customs_clearance=shipment["customs_clearance"],
        )

        au_result = calculate_au_charges(
            rules=au_rules,
            chargeable_weight=shipment["chargeable_weight"],
            cargo_handling=shipment["cargo_handling"],
            service_type=shipment["service_type"],
            mawb_count=shipment["mawb_count"],
            hawb_count=shipment["hawb_count"],
            consol_count=1,
            cto=shipment["cto"],
            dg=shipment["dg"], sac=shipment["sac"],
            tranship=shipment["tranship"],
            late_reporting=shipment["late_reporting"],
            manual_registration=shipment["manual_registration"],
            quarantine=shipment["quarantine"],
            quarantine_minutes=shipment["quarantine_minutes"],
            palletise=shipment["palletise"],
            shrink_wrap=shipment["shrink_wrap"],
            pallet_count=shipment["pallet_count"],
            labelling_au=shipment["labelling_au"],
            label_pieces=shipment["label_pieces"],
            label_basis=shipment["label_basis"],
            photos=shipment["photos"],
            third_party_connote=shipment["third_party_connote"],
            connote_count=shipment["connote_count"],
            cartage=shipment["cartage"],
            fsc_aud=shipment["fsc_aud"],
            storage=shipment["storage"],
            storage_days=shipment["storage_days"],
            undeclared_dg=False,
            document_processing=False,
            xray_repack=False,
            skid_count=1,
            weekend_collection=shipment["weekend_collection"],
            buildup=shipment["buildup"],
            handover_bond=shipment["handover_bond"],
        )

        freight_usd = float(selected["base_freight_usd"])
        origin_usd = float(origin_result["total_usd"])
        au_aud = float(au_result["total_aud"])
        usd_subtotal = freight_usd + origin_usd
        converted_aud = usd_subtotal * shipment["exchange_rate"]
        total_aud = converted_aud + au_aud

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Chargeable Weight", f"{shipment['chargeable_weight']:,.2f} kg")
        m2.metric("Air Freight", f"USD {freight_usd:,.2f}")
        m3.metric("AU Charges", f"AUD {au_aud:,.2f}")
        m4.metric("TOTAL QUOTATION", f"AUD {total_aud:,.2f}")

        b1, b2, b3 = st.columns(3)
        with b1:
            st.markdown("#### ✈️ Air Freight")
            st.write(f"**{selected['airline']}** — {selected['routing']}")
            st.write(f"Break: **{selected['bracket']}**")
            st.write(f"Rate: **USD {selected['rate_per_kg']:,.4f}/kg**")
            st.write(f"Weight freight: **USD {selected['weight_freight_usd']:,.2f}**")
            st.write(f"Minimum: **USD {selected['minimum_usd']:,.2f}**")
            st.write(f"Applied: **USD {freight_usd:,.2f}**")
            st.caption(f"Source row: Import Tarrif.xlsx / INDIA / {selected['source_row']}")

        with b2:
            st.markdown("#### 📦 Origin Charges")
            for item in origin_result["items"]:
                st.write(f"**{item['name']}** — {item['display']}")
            st.markdown(f"**Origin total: USD {origin_usd:,.2f}**")

        with b3:
            st.markdown("#### 🇦🇺 Australian Charges")
            for item in au_result["items"]:
                st.write(f"**{item['name']}** — {item['display']}")
            if au_result["flags"]:
                for flag in au_result["flags"]:
                    st.warning(flag)
            st.markdown(f"**AU total: AUD {au_aud:,.2f}**")

        st.markdown("#### Currency Conversion")
        st.write(
            f"USD subtotal **USD {usd_subtotal:,.2f}** × FX **{shipment['exchange_rate']:.4f}** "
            f"= **AUD {converted_aud:,.2f}**"
        )

        st.success(f"## Final Quotation: AUD {total_aud:,.2f}")

        all_quote_rows.append({
            "shipment": idx,
            "origin": shipment["origin"], "destination": shipment["destination"],
            "weight": shipment["chargeable_weight"],
            "airline": selected["airline"], "routing": selected["routing"],
            "freight_usd": freight_usd, "origin_usd": origin_usd,
            "au_aud": au_aud, "exchange_rate": shipment["exchange_rate"],
            "total_aud": total_aud,
        })

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🗑️ Clear Quote", use_container_width=True):
            st.session_state.shipments = []
            st.rerun()
    with c2:
        if all_quote_rows:
            pdf = build_quote_pdf(all_quote_rows, "Air Freight Quotation")
            st.download_button(
                "📄 Generate Quotation PDF",
                data=pdf,
                file_name="air_freight_quotation.pdf",
                mime="application/pdf",
                use_container_width=True,
            )


from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def build_quote_pdf(rows, title="Air Freight Quotation"):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="Small",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
    ))

    story = [
        Paragraph(title, styles["Title"]),
        Paragraph("India → Australia Import Air Freight", styles["Heading2"]),
        Spacer(1, 8),
    ]

    data = [[
        "Shipment", "Route", "Wt kg", "Airline", "Freight USD",
        "Origin USD", "AU AUD", "FX", "Total AUD"
    ]]

    grand_total = 0.0

    for r in rows:
        grand_total += r["total_aud"]
        data.append([
            str(r["shipment"]),
            f"{r['origin']} → {r['destination']}",
            f"{r['weight']:.2f}",
            f"{r['airline']} / {r['routing']}",
            f"{r['freight_usd']:,.2f}",
            f"{r['origin_usd']:,.2f}",
            f"{r['au_aud']:,.2f}",
            f"{r['exchange_rate']:.4f}",
            f"{r['total_aud']:,.2f}",
        ])

    table = Table(data, repeatRows=1, colWidths=[12*mm, 24*mm, 15*mm, 42*mm, 23*mm, 23*mm, 23*mm, 18*mm, 25*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
    ]))

    story.append(table)
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        f"<b>Grand Total: AUD {grand_total:,.2f}</b>",
        styles["Heading2"],
    ))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Quotation currency: AUD. USD components are converted using the exchange rate shown for each shipment.",
        styles["Small"],
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Rates are calculated from the supplied tariff files. Charges marked On Application / On Request or otherwise lacking a safe calculation basis are excluded and flagged in the application.",
        styles["Small"],
    ))

    doc.build(story)
    return buffer.getvalue()

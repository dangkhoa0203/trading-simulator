"""Portfolio PDF statement rendering.

Was a separate stateless microservice (ECS/Fargate, called over HTTP) when this ran on AWS —
folded in-process here since there's no longer an orchestrator making that separation pay for
itself. Same reportlab output, just called as a function instead of a POST.
"""

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Terminal statement style — dark ink on white, amber accent rules, monospace figures.
# Mirrors the "Terminal" direction from the app's own theme (frontend/css/style.css).
INK = colors.HexColor("#14181a")
SOFT = colors.HexColor("#5b6467")
RULE = colors.HexColor("#d8dcdb")
ACCENT = colors.HexColor("#d99414")
GAIN = colors.HexColor("#1f7a5c")
LOSS = colors.HexColor("#a93a2e")

STYLES = {
    "brand": ParagraphStyle("brand", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=ACCENT, spaceAfter=4),
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=INK, spaceAfter=4),
    "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=9.5, leading=13, textColor=SOFT, spaceAfter=20),
    "section": ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=SOFT, spaceAfter=8),
    "footer": ParagraphStyle("footer", fontName="Helvetica", fontSize=8, leading=11, textColor=SOFT, alignment=TA_CENTER),
    "empty": ParagraphStyle("empty", fontName="Courier", fontSize=9.5, leading=13, textColor=SOFT),
}


def _money(value):
    return f"${value:,.2f}"


def _section_label(text):
    table = Table([[Paragraph(text.upper(), STYLES["section"])]], colWidths=[6.4 * inch])
    table.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, -1), 1.5, ACCENT),
    ]))
    return table


def _data_table(rows, col_widths, num_cols=(), side_col=None):
    """rows[0] is the header. num_cols are right-aligned/tabular; side_col is BUY/SELL colored."""
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    style = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), SOFT),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, ACCENT),
        ("FONTNAME", (0, 1), (-1, -1), "Courier"),
        ("FONTSIZE", (0, 1), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("LINEBELOW", (0, 1), (-1, -2), 0.5, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for col in num_cols:
        style.append(("ALIGN", (col, 0), (col, -1), "RIGHT"))
    if side_col is not None:
        for row_idx, row in enumerate(rows[1:], start=1):
            color = GAIN if row[side_col] == "BUY" else LOSS
            style.append(("TEXTCOLOR", (side_col, row_idx), (side_col, row_idx), color))
            style.append(("FONTNAME", (side_col, row_idx), (side_col, row_idx), "Courier-Bold"))
    table.setStyle(TableStyle(style))
    return table


def build_pdf(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    )
    story = []

    portfolio = data["portfolio"]
    story.append(Paragraph("TRADENOW", STYLES["brand"]))
    story.append(Paragraph(portfolio["name"], STYLES["title"]))
    story.append(
        Paragraph(
            f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            STYLES["meta"],
        )
    )

    story.append(_section_label("Summary"))
    story.append(Spacer(1, 8))
    summary_rows = [
        ["Cash balance", _money(portfolio["cash_balance"])],
        ["Total value", _money(portfolio["total_value"])],
        ["Base currency", portfolio.get("base_currency", "USD")],
    ]
    summary_table = Table(summary_rows, colWidths=[2.4 * inch, 4 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica"),
                ("TEXTCOLOR", (0, 0), (0, -1), SOFT),
                ("FONTNAME", (1, 0), (1, -1), "Courier-Bold"),
                ("TEXTCOLOR", (1, 0), (1, -1), INK),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 24))

    story.append(_section_label("Holdings"))
    story.append(Spacer(1, 4))
    holdings = data.get("holdings", [])
    if holdings:
        rows = [["TICKER", "QUANTITY", "AVG COST", "CURRENT PRICE", "MARKET VALUE"]]
        for h in holdings:
            rows.append(
                [
                    h["symbol"],
                    str(h["quantity"]),
                    _money(h["avg_cost"]),
                    _money(h["current_price"]) if h.get("current_price") is not None else "—",
                    _money(h["market_value"]) if h.get("market_value") is not None else "—",
                ]
            )
        story.append(_data_table(
            rows,
            [1.1 * inch, 1.1 * inch, 1.2 * inch, 1.5 * inch, 1.5 * inch],
            num_cols=(1, 2, 3, 4),
        ))
    else:
        story.append(Paragraph("No holdings.", STYLES["empty"]))
    story.append(Spacer(1, 24))

    story.append(_section_label("Transaction history"))
    story.append(Spacer(1, 4))
    transactions = data.get("transactions", [])
    if transactions:
        rows = [["DATE", "TICKER", "SIDE", "QUANTITY", "PRICE"]]
        for t in transactions:
            rows.append(
                [
                    t.get("executed_at", "")[:10],
                    t["symbol"],
                    t["side"],
                    str(t["quantity"]),
                    _money(t["price"]),
                ]
            )
        story.append(_data_table(
            rows,
            [1.3 * inch, 1.1 * inch, 1 * inch, 1.3 * inch, 1.3 * inch],
            num_cols=(3, 4),
            side_col=2,
        ))
    else:
        story.append(Paragraph("No transactions.", STYLES["empty"]))

    story.append(Spacer(1, 28))
    story.append(Paragraph(
        "TradeNow — simulated portfolio statement. Prices reflect data available at generation time.",
        STYLES["footer"],
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer

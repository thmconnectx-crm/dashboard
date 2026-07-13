from datetime import date, datetime
from io import BytesIO
import math

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import CampaignMetric


BRAND_DARK = colors.HexColor("#0B1117")
BRAND_PANEL = colors.HexColor("#111A22")
BRAND_GREEN = colors.HexColor("#35D092")
BRAND_CYAN = colors.HexColor("#39B8D8")
BRAND_AMBER = colors.HexColor("#F0B76B")
BRAND_LINE = colors.HexColor("#D9E1E8")
BRAND_SOFT = colors.HexColor("#F4F7FA")
BRAND_MUTED = colors.HexColor("#5B6874")


def rows_to_dataframe(rows: list[CampaignMetric]) -> pd.DataFrame:
    data = [
        {
            "Data": row.date,
            "Plataforma": _platform_label(row.platform),
            "Conta": row.account_id,
            "Campanha": row.campaign_name,
            "Modelo da Campanha": _objective_label(getattr(row, "campaign_objective", "")),
            "Objetivo técnico": getattr(row, "campaign_objective", ""),
            "Alcance": getattr(row, "reach", 0),
            "Impressões": row.impressions,
            "Frequência": _safe_div(row.impressions, getattr(row, "reach", 0)),
            "Cliques": row.clicks,
            "CTR (%)": row.ctr,
            "CPC": row.cpc,
            "Investimento": row.spend,
            "Mensagens": getattr(row, "messages", 0.0),
            "Custo por Mensagem": getattr(row, "cost_per_message", 0.0),
            "Conversões": row.conversions,
            "Custo/Conv.": row.cost_per_conversion,
            "Valor de Conversão": row.conversion_value,
            "ROAS": row.roas,
        }
        for row in rows
    ]
    return pd.DataFrame(data)


def build_excel(rows: list[CampaignMetric]) -> bytes:
    df = rows_to_dataframe(rows)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if df.empty:
            pd.DataFrame([{"Status": "Nenhum dado encontrado para os filtros selecionados."}]).to_excel(
                writer, index=False, sheet_name="Resumo"
            )
        else:
            platform_summary = _aggregate(df, ["Plataforma"])
            campaign_summary = _aggregate(df, ["Plataforma", "Conta", "Modelo da Campanha", "Campanha"]).sort_values(
                by="Investimento", ascending=False
            )
            daily_summary = _aggregate(df, ["Data", "Plataforma"]).sort_values(by=["Data", "Plataforma"])

            overview = pd.DataFrame(
                [
                    {"Indicador": "Investimento total", "Valor": _money(float(df["Investimento"].sum()))},
                    {"Indicador": "Mensagens iniciadas", "Valor": _number(float(df["Mensagens"].sum()))},
                    {"Indicador": "Custo por mensagem", "Valor": _money(_safe_div(df["Investimento"].sum(), df["Mensagens"].sum()))},
                    {"Indicador": "Alcance", "Valor": _integer(float(df["Alcance"].sum()))},
                    {"Indicador": "Impressões", "Valor": _integer(float(df["Impressões"].sum()))},
                    {"Indicador": "Frequência", "Valor": _ratio(_safe_div(df["Impressões"].sum(), df["Alcance"].sum()))},
                    {"Indicador": "CTR médio", "Valor": _percent(_safe_div(df["Cliques"].sum(), df["Impressões"].sum()) * 100)},
                    {"Indicador": "CPC médio", "Valor": _money(_safe_div(df["Investimento"].sum(), df["Cliques"].sum()))},
                ]
            )
            overview.to_excel(writer, index=False, sheet_name="Resumo")
            platform_summary.to_excel(writer, index=False, sheet_name="Plataformas")
            campaign_summary.to_excel(writer, index=False, sheet_name="Campanhas")
            daily_summary.to_excel(writer, index=False, sheet_name="Evolução diária")
            df.sort_values(by=["Data", "Plataforma", "Campanha"]).to_excel(writer, index=False, sheet_name="Histórico")

        for worksheet in writer.book.worksheets:
            _style_worksheet(worksheet)
    return output.getvalue()


def build_pdf(rows: list[CampaignMetric], start_date: date | None = None, end_date: date | None = None) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Relatório de Campanhas de Mensagens",
        author="Paid Traffic Dashboard",
    )
    styles = _pdf_styles()
    story: list = []
    df = rows_to_dataframe(rows)
    period = _period_label(start_date, end_date)

    story.extend(_pdf_header(styles, period))

    if df.empty:
        story.extend(
            [
                Spacer(1, 16),
                Paragraph("Nenhum dado encontrado para os filtros selecionados.", styles["Empty"]),
                Paragraph(
                    "Verifique o período, a conta selecionada ou execute uma nova sincronização antes de exportar o relatório.",
                    styles["BodyMuted"],
                ),
            ]
        )
        document.build(story, onFirstPage=_footer, onLaterPages=_footer)
        return output.getvalue()

    platform_summary = _aggregate(df, ["Plataforma"])
    campaign_summary = _aggregate(df, ["Plataforma", "Conta", "Modelo da Campanha", "Campanha"]).sort_values(by="Investimento", ascending=False)
    daily_summary = _aggregate(df, ["Data", "Plataforma"]).sort_values(by=["Data", "Plataforma"])

    totals = _totals(df)
    story.append(_kpi_cards(totals, styles))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Leitura executiva", styles["SectionTitle"]))
    story.extend(_executive_reading(df, campaign_summary, platform_summary, styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Resumo por plataforma", styles["SectionTitle"]))
    story.append(
        _data_table(
            platform_summary,
            ["Plataforma", "Investimento", "Mensagens", "Custo por Mensagem", "Alcance", "Impressões", "Frequência", "Cliques", "CTR (%)", "CPC"],
            money_cols={"Investimento", "Custo por Mensagem", "CPC"},
            percent_cols={"CTR (%)"},
            width=258 * mm,
        )
    )
    story.append(Spacer(1, 12))

    story.append(Paragraph("Top campanhas por investimento", styles["SectionTitle"]))
    story.append(
        _data_table(
            campaign_summary.head(12),
            ["Plataforma", "Modelo da Campanha", "Campanha", "Investimento", "Mensagens", "Custo por Mensagem", "Alcance", "Frequência", "Cliques", "CTR (%)"],
            money_cols={"Investimento", "Custo por Mensagem"},
            percent_cols={"CTR (%)"},
            width=258 * mm,
            wrap_cols={"Modelo da Campanha", "Campanha"},
        )
    )

    story.append(PageBreak())
    story.append(Paragraph("Evolução diária por plataforma", styles["SectionTitle"]))
    story.append(
        _data_table(
            daily_summary.tail(30),
            ["Data", "Plataforma", "Investimento", "Mensagens", "Custo por Mensagem", "Alcance", "Impressões", "Frequência", "Cliques", "CTR (%)"],
            money_cols={"Investimento", "Custo por Mensagem"},
            percent_cols={"CTR (%)"},
            width=258 * mm,
        )
    )
    story.append(Spacer(1, 12))

    story.append(Paragraph("Detalhamento consolidado por campanha", styles["SectionTitle"]))
    story.append(
        _data_table(
            campaign_summary,
            ["Plataforma", "Conta", "Modelo da Campanha", "Campanha", "Alcance", "Impressões", "Frequência", "Cliques", "CTR (%)", "CPC", "Investimento", "Mensagens", "Custo por Mensagem"],
            money_cols={"Investimento", "CPC", "Custo por Mensagem"},
            percent_cols={"CTR (%)"},
            width=258 * mm,
            wrap_cols={"Modelo da Campanha", "Campanha"},
            max_rows=60,
        )
    )
    if len(campaign_summary) > 60:
        story.append(
            Paragraph(
                f"O relatório exibe as 60 principais campanhas por investimento. A exportação em Excel contém a base completa com {len(campaign_summary)} campanhas.",
                styles["BodyMuted"],
            )
        )

    document.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return output.getvalue()


def _aggregate(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    grouped = df.groupby(group_cols, as_index=False).agg(
        {
            "Impressões": "sum",
            "Alcance": "sum",
            "Cliques": "sum",
            "Investimento": "sum",
            "Mensagens": "sum",
            "Conversões": "sum",
            "Valor de Conversão": "sum",
        }
    )
    grouped["CTR (%)"] = grouped.apply(lambda row: _safe_div(row["Cliques"], row["Impressões"]) * 100, axis=1)
    grouped["Frequência"] = grouped.apply(lambda row: _safe_div(row["Impressões"], row["Alcance"]), axis=1)
    grouped["CPC"] = grouped.apply(lambda row: _safe_div(row["Investimento"], row["Cliques"]), axis=1)
    grouped["Custo por Mensagem"] = grouped.apply(lambda row: _safe_div(row["Investimento"], row["Mensagens"]), axis=1)
    grouped["Custo/Conv."] = grouped.apply(lambda row: _safe_div(row["Investimento"], row["Conversões"]), axis=1)
    grouped["ROAS"] = grouped.apply(lambda row: _safe_div(row["Valor de Conversão"], row["Investimento"]), axis=1)
    return grouped.round({"CTR (%)": 2, "Frequência": 2, "CPC": 2, "Custo por Mensagem": 2, "Custo/Conv.": 2, "ROAS": 2, "Investimento": 2, "Valor de Conversão": 2, "Mensagens": 2, "Conversões": 2})


def _totals(df: pd.DataFrame) -> dict[str, float]:
    spend = float(df["Investimento"].sum())
    conversions = float(df["Conversões"].sum())
    messages = float(df["Mensagens"].sum())
    value = float(df["Valor de Conversão"].sum())
    clicks = float(df["Cliques"].sum())
    impressions = float(df["Impressões"].sum())
    reach = float(df["Alcance"].sum())
    return {
        "spend": spend,
        "reach": reach,
        "impressions": impressions,
        "messages": messages,
        "cost_per_message": _safe_div(spend, messages),
        "conversions": conversions,
        "value": value,
        "roas": _safe_div(value, spend),
        "ctr": _safe_div(clicks, impressions) * 100,
        "cpc": _safe_div(spend, clicks),
        "cpa": _safe_div(spend, conversions),
    }


def _pdf_header(styles: dict, period: str) -> list:
    title_table = Table(
        [
            [
                Paragraph("RELATÓRIO PREMIUM DE CAMPANHAS DE MENSAGENS", styles["HeaderKicker"]),
                Paragraph(f"Período analisado<br/><b>{period}</b>", styles["HeaderMeta"]),
            ],
            [
                Paragraph("Performance de campanhas para mensagens", styles["HeaderTitle"]),
                Paragraph(f"Gerado em<br/><b>{datetime.now().strftime('%d/%m/%Y às %H:%M')}</b>", styles["HeaderMeta"]),
            ],
            [
                Paragraph("Meta Ads e Google Ads | Alcance, impressões, cliques, mensagens iniciadas e custo por conversa.", styles["HeaderSubtitle"]),
                "",
            ],
        ],
        colWidths=[183 * mm, 75 * mm],
        hAlign="LEFT",
    )
    title_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BRAND_DARK),
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#24313D")),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#24313D")),
                ("SPAN", (0, 2), (-1, 2)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return [title_table, Spacer(1, 12)]


def _kpi_cards(totals: dict[str, float], styles: dict) -> Table:
    cards = [
        ("Investimento total", _money(totals["spend"]), "Aplicação consolidada no período"),
        ("Mensagens", _number(totals["messages"]), "Conversas iniciadas pela campanha"),
        ("Custo por mensagem", _money(totals["cost_per_message"]), "Eficiência principal para WhatsApp/Direct"),
        ("CTR / CPC", f"{_percent(totals['ctr'])} | {_money(totals['cpc'])}", "Clique e custo médio por clique"),
    ]
    table = Table(
        [
            [
                [
                    Paragraph(label, styles["KpiLabel"]),
                    Paragraph(value, styles["KpiValue"]),
                    Paragraph(note, styles["KpiNote"]),
                ]
                for label, value, note in cards
            ]
        ],
        colWidths=[64.5 * mm] * 4,
        rowHeights=[26 * mm],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.45, BRAND_LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5EBF0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _executive_reading(df: pd.DataFrame, campaign_summary: pd.DataFrame, platform_summary: pd.DataFrame, styles: dict) -> list:
    totals = _totals(df)
    best_platform = platform_summary.sort_values(by="Custo por Mensagem", ascending=True).iloc[0]
    top_campaign = campaign_summary.iloc[0]
    bullets = [
        f"No período analisado, o investimento total foi de <b>{_money(totals['spend'])}</b>, gerando <b>{_number(totals['messages'])}</b> mensagens iniciadas.",
        f"O custo médio por mensagem ficou em <b>{_money(totals['cost_per_message'])}</b>, com alcance total de <b>{_integer(totals['reach'])}</b> pessoas, <b>{_integer(totals['impressions'])}</b> impressões e frequência média de <b>{_ratio(_safe_div(totals['impressions'], totals['reach']))}</b>.",
        f"A plataforma mais eficiente em custo por mensagem foi <b>{best_platform['Plataforma']}</b>, com <b>{_money(float(best_platform['Custo por Mensagem']))}</b> por conversa iniciada.",
        f"A campanha com maior investimento foi <b>{_escape(str(top_campaign['Campanha']))}</b>, com <b>{_money(float(top_campaign['Investimento']))}</b> aplicados.",
        f"O CTR médio consolidado foi de <b>{_percent(totals['ctr'])}</b> e o CPC médio ficou em <b>{_money(totals['cpc'])}</b>.",
    ]
    return [Paragraph(f"• {item}", styles["Body"]) for item in bullets]


def _data_table(
    df: pd.DataFrame,
    columns: list[str],
    money_cols: set[str] | None = None,
    percent_cols: set[str] | None = None,
    wrap_cols: set[str] | None = None,
    width: float = 258 * mm,
    max_rows: int | None = None,
) -> Table:
    money_cols = money_cols or set()
    percent_cols = percent_cols or set()
    wrap_cols = wrap_cols or set()
    data = df[columns].head(max_rows).copy() if max_rows else df[columns].copy()
    header = [Paragraph(str(col), _pdf_styles()["TableHeader"]) for col in columns]
    rows = []
    for _, item in data.iterrows():
        row = []
        for col in columns:
            value = item[col]
            if col == "Data" and hasattr(value, "strftime"):
                text = value.strftime("%d/%m/%Y")
            elif col in money_cols:
                text = _money(float(value))
            elif col in percent_cols:
                text = _percent(float(value))
            elif col in {"ROAS", "Frequência"}:
                text = _ratio(float(value))
            elif col in {"Alcance", "Impressões", "Cliques"}:
                text = _integer(float(value))
            elif col in {"Mensagens", "Conversões"}:
                text = _number(float(value))
            else:
                text = str(value)
            row.append(Paragraph(_escape(text), _pdf_styles()["TableCell"]) if col in wrap_cols else text)
        rows.append(row)

    col_widths = _column_widths(columns, width)
    table = Table([header] + rows, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_PANEL),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BRAND_SOFT]),
                ("GRID", (0, 0), (-1, -1), 0.25, BRAND_LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    for index, col in enumerate(columns):
        if col not in {"Plataforma", "Conta", "Modelo da Campanha", "Campanha", "Data"}:
            table.setStyle(TableStyle([("ALIGN", (index, 1), (index, -1), "RIGHT")]))
    return table


def _column_widths(columns: list[str], width: float) -> list[float]:
    weights = {
        "Campanha": 3.6,
        "Conta": 1.5,
        "Plataforma": 1.25,
        "Data": 1.1,
        "Modelo da Campanha": 1.65,
        "Valor de Conversão": 1.7,
        "Investimento": 1.55,
        "Custo por Mensagem": 1.7,
        "Custo/Conv.": 1.45,
        "Mensagens": 1.2,
        "Impressões": 1.25,
        "Alcance": 1.2,
        "Frequência": 1.2,
    }
    total = sum(weights.get(col, 1.15) for col in columns)
    return [width * (weights.get(col, 1.15) / total) for col in columns]


def _pdf_styles() -> dict:
    base = getSampleStyleSheet()
    base.add(
        ParagraphStyle(
            "HeaderKicker",
            parent=base["Normal"],
            textColor=BRAND_GREEN,
            fontSize=8,
            leading=10,
            fontName="Helvetica-Bold",
            uppercase=True,
        )
    )
    base.add(ParagraphStyle("HeaderTitle", parent=base["Title"], textColor=colors.white, fontSize=24, leading=27, fontName="Helvetica-Bold"))
    base.add(ParagraphStyle("HeaderSubtitle", parent=base["Normal"], textColor=colors.HexColor("#C9D4DD"), fontSize=9.5, leading=13))
    base.add(ParagraphStyle("HeaderMeta", parent=base["Normal"], textColor=colors.HexColor("#DCE6ED"), fontSize=8.5, leading=12, alignment=TA_RIGHT))
    base.add(ParagraphStyle("SectionTitle", parent=base["Heading2"], textColor=BRAND_DARK, fontSize=12, leading=15, spaceBefore=4, spaceAfter=7))
    base.add(ParagraphStyle("Body", parent=base["Normal"], textColor=colors.HexColor("#22303A"), fontSize=9, leading=13, spaceAfter=5))
    base.add(ParagraphStyle("BodyMuted", parent=base["Normal"], textColor=BRAND_MUTED, fontSize=8.4, leading=12, spaceAfter=5))
    base.add(ParagraphStyle("Empty", parent=base["Heading2"], textColor=BRAND_DARK, fontSize=15, leading=18, alignment=TA_CENTER, spaceAfter=8))
    base.add(ParagraphStyle("KpiLabel", parent=base["Normal"], textColor=BRAND_MUTED, fontSize=7.8, leading=9, fontName="Helvetica-Bold"))
    base.add(ParagraphStyle("KpiValue", parent=base["Normal"], textColor=BRAND_DARK, fontSize=13, leading=15, fontName="Helvetica-Bold"))
    base.add(ParagraphStyle("KpiNote", parent=base["Normal"], textColor=BRAND_MUTED, fontSize=7.2, leading=9))
    base.add(ParagraphStyle("TableHeader", parent=base["Normal"], textColor=colors.white, fontSize=7.2, leading=8.5, fontName="Helvetica-Bold"))
    base.add(ParagraphStyle("TableCell", parent=base["Normal"], textColor=colors.HexColor("#1D2933"), fontSize=7.1, leading=8.5))
    return base


def _style_worksheet(worksheet) -> None:
    header_fill = PatternFill("solid", fgColor="111A22")
    header_font = Font(color="FFFFFF", bold=True)
    soft_fill = PatternFill("solid", fgColor="F4F7FA")
    thin = Side(style="thin", color="D9E1E8")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    worksheet.freeze_panes = "A2"
    for row in worksheet.iter_rows():
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(vertical="center", wrap_text=False)
            if cell.row == 1:
                cell.fill = header_fill
                cell.font = header_font
            elif cell.row % 2 == 0:
                cell.fill = soft_fill
    for column_cells in worksheet.columns:
        max_length = 0
        column = column_cells[0].column
        for cell in column_cells:
            max_length = max(max_length, len(str(cell.value or "")))
        worksheet.column_dimensions[get_column_letter(column)].width = min(max(max_length + 2, 12), 38)
    worksheet.sheet_view.showGridLines = False


def _footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D9E1E8"))
    canvas.line(document.leftMargin, 11 * mm, landscape(A4)[0] - document.rightMargin, 11 * mm)
    canvas.setFillColor(BRAND_MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(document.leftMargin, 6 * mm, "Paid Traffic Dashboard | Relatório gerado automaticamente")
    canvas.drawRightString(landscape(A4)[0] - document.rightMargin, 6 * mm, f"Página {document.page}")
    canvas.restoreState()


def _platform_label(value: str) -> str:
    return "Google Ads" if value == "google" else "Meta Ads" if value == "meta" else value.title()


def _objective_label(value: str) -> str:
    normalized = (value or "").strip().upper()
    if normalized in {"OUTCOME_ENGAGEMENT", "MESSAGES", "POST_ENGAGEMENT"}:
        return "Engajamento para mensagens"
    if normalized in {"OUTCOME_LEADS", "LEAD_GENERATION"}:
        return "Geração de cadastros"
    if normalized in {"OUTCOME_TRAFFIC", "LINK_CLICKS"}:
        return "Tráfego"
    if normalized in {"OUTCOME_SALES", "CONVERSIONS"}:
        return "Vendas / conversões"
    if normalized in {"OUTCOME_AWARENESS", "BRAND_AWARENESS", "REACH"}:
        return "Reconhecimento / alcance"
    return value.replace("_", " ").title() if value else "Não informado"


def _period_label(start_date: date | None, end_date: date | None) -> str:
    if start_date and end_date:
        return f"{start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}"
    return "Período selecionado"


def _safe_div(numerator: float, denominator: float) -> float:
    try:
        if not denominator or math.isclose(float(denominator), 0.0):
            return 0.0
        value = float(numerator) / float(denominator)
        return value if math.isfinite(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _money(value: float) -> str:
    return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _integer(value: float) -> str:
    return f"{int(round(float(value))):,}".replace(",", ".")


def _number(value: float) -> str:
    return f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _percent(value: float) -> str:
    return f"{float(value):.2f}%".replace(".", ",")


def _ratio(value: float) -> str:
    return f"{float(value):.2f}".replace(".", ",")


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

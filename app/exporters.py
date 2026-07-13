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


def build_pdf(
    rows: list[CampaignMetric],
    start_date: date | None = None,
    end_date: date | None = None,
    previous_rows: list[CampaignMetric] | None = None,
) -> bytes:
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

    previous_df = rows_to_dataframe(previous_rows or [])
    campaign_summary = _aggregate(df, ["Plataforma", "Conta", "Modelo da Campanha", "Campanha"]).sort_values(by="Investimento", ascending=False)
    daily_summary = _aggregate(df, ["Data", "Plataforma"]).sort_values(by=["Data", "Plataforma"])

    story.append(_comparison_cards(df, previous_df, campaign_summary, styles))
    story.append(Spacer(1, 8))
    story.append(_campaign_overview(campaign_summary, styles))
    story.append(Spacer(1, 8))

    left_col = [
        Paragraph("Conversões e ações por tipo", styles["SectionTitle"]),
        _actions_table(df, styles),
        Spacer(1, 8),
        Paragraph("Distribuição por campanha", styles["SectionTitle"]),
        _mini_bar_table(campaign_summary.head(6), "Campanha", "Mensagens", "Custo por Mensagem", styles),
    ]
    right_col = [
        Paragraph("Alcance e impressões", styles["SectionTitle"]),
        _mini_bar_table(campaign_summary.head(6), "Campanha", "Alcance", "Impressões", styles),
        Spacer(1, 8),
        Paragraph("Evolução diária", styles["SectionTitle"]),
        _mini_bar_table(daily_summary.tail(8), "Data", "Mensagens", "Cliques", styles),
    ]
    columns = Table([[left_col, right_col]], colWidths=[126 * mm, 126 * mm], hAlign="LEFT")
    columns.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(columns)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Campanhas em destaque", styles["SectionTitle"]))
    story.append(_featured_campaigns_table(campaign_summary.head(12), styles))

    try:
        document.build(story, onFirstPage=_footer, onLaterPages=_footer)
    except Exception:
        output = BytesIO()
        fallback = SimpleDocTemplate(
            output,
            pagesize=landscape(A4),
            rightMargin=18 * mm,
            leftMargin=18 * mm,
            topMargin=14 * mm,
            bottomMargin=14 * mm,
            title="Relatório de Campanhas de Mensagens",
            author="Paid Traffic Dashboard",
        )
        fallback.build(_fallback_pdf_story(df, period, styles), onFirstPage=_footer, onLaterPages=_footer)
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


def _totals_from_summary(df: pd.DataFrame) -> dict[str, float]:
    spend = float(df["Investimento"].sum()) if "Investimento" in df else 0.0
    messages = float(df["Mensagens"].sum()) if "Mensagens" in df else 0.0
    clicks = float(df["Cliques"].sum()) if "Cliques" in df else 0.0
    impressions = float(df["Impressões"].sum()) if "Impressões" in df else 0.0
    reach = float(df["Alcance"].sum()) if "Alcance" in df else 0.0
    return {
        "spend": spend,
        "messages": messages,
        "reach": reach,
        "impressions": impressions,
        "clicks": clicks,
        "cpc": _safe_div(spend, clicks),
        "ctr": _safe_div(clicks, impressions) * 100,
        "cost_per_message": _safe_div(spend, messages),
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


def _comparison_cards(df: pd.DataFrame, previous_df: pd.DataFrame, campaign_summary: pd.DataFrame, styles: dict) -> Table:
    current = _totals(df)
    previous = _totals(previous_df) if not previous_df.empty else {}
    cards = [
        ("Valor investido", _money(current["spend"]), previous.get("spend", 0), current["spend"], _money),
        ("Impressões", _integer(current["impressions"]), previous.get("impressions", 0), current["impressions"], _integer),
        ("Cliques", _integer(current["clicks"]), previous.get("clicks", 0), current["clicks"], _integer),
        ("Número de campanhas", _integer(len(campaign_summary)), len(_aggregate(previous_df, ["Campanha"])) if not previous_df.empty else 0, len(campaign_summary), _integer),
    ]
    cells = []
    for label, value, old_value, new_value, formatter in cards:
        delta = _delta(new_value, old_value)
        previous_label = f"{formatter(old_value)} no período anterior" if old_value else "Sem período anterior"
        cells.append(Paragraph(f"<b>{_escape(label)}</b><br/><font size='15'>{_escape(value)}</font><br/><font color='#35D092'><b>{_escape(delta)}</b></font><br/><font color='#5B6874'>{_escape(previous_label)}</font>", styles["KpiCard"]))
    table = Table([cells], colWidths=[64.5 * mm] * 4, rowHeights=[31 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.5, BRAND_LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, BRAND_LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _campaign_overview(campaign_summary: pd.DataFrame, styles: dict) -> Table:
    totals = _totals_from_summary(campaign_summary)
    campaign_names = "<br/>".join(_escape(name) for name in campaign_summary["Campanha"].head(4).tolist()) or "Campanhas selecionadas"
    metrics = [
        ("Alcance total", _integer(totals["reach"])),
        ("Impressões totais", _integer(totals["impressions"])),
        ("Total de cliques", _integer(totals["clicks"])),
        ("Valor investido", _money(totals["spend"])),
        ("CPC médio total", _money(totals["cpc"])),
        ("CTR (todos)", _percent(totals["ctr"])),
        ("CPM médio", _money(_safe_div(totals["spend"] * 1000, totals["impressions"]))),
        ("Frequência", _ratio(_safe_div(totals["impressions"], totals["reach"]))),
    ]
    metric_cells = [
        [Paragraph(label, styles["SmallLabel"]), Paragraph(value, styles["SmallValue"])]
        for label, value in metrics
    ]
    metric_grid = Table(
        [metric_cells[:4], metric_cells[4:]],
        colWidths=[27 * mm] * 4,
        rowHeights=[17 * mm, 17 * mm],
    )
    metric_grid.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BRAND_SOFT),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, BRAND_LINE),
                ("BOX", (0, 0), (-1, -1), 0.25, BRAND_LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    table = Table(
        [[Paragraph("Campanhas", styles["SectionTitle"]), Paragraph(campaign_names, styles["Body"]), metric_grid]],
        colWidths=[31 * mm, 86 * mm, 136 * mm],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.5, BRAND_LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _actions_table(df: pd.DataFrame, styles: dict) -> Table:
    totals = _totals(df)
    rows = [
        ["Tipo", "Total", "Custo por ação"],
        ["Mensagens iniciadas", _number(totals["messages"]), _money(totals["cost_per_message"])],
        ["Cliques nos links", _integer(totals["clicks"]), _money(totals["cpc"])],
        ["Pessoas alcançadas", _integer(totals["reach"]), _money(_safe_div(totals["spend"], totals["reach"]))],
        ["Impressões", _integer(totals["impressions"]), _money(_safe_div(totals["spend"] * 1000, totals["impressions"])) + " CPM"],
    ]
    return _plain_table(rows, [58 * mm, 32 * mm, 35 * mm], styles)


def _mini_bar_table(df: pd.DataFrame, label_col: str, value_col: str, second_col: str, styles: dict) -> Table:
    rows = [[label_col, value_col, second_col]]
    for _, row in df.iterrows():
        label = row[label_col].strftime("%d/%m") if label_col == "Data" and hasattr(row[label_col], "strftime") else str(row[label_col])
        rows.append([_clip(label, 34), _format_metric(value_col, row[value_col]), _format_metric(second_col, row[second_col])])
    if len(rows) == 1:
        rows.append(["Sem dados", "-", "-"])
    return _plain_table(rows, [58 * mm, 32 * mm, 35 * mm], styles)


def _featured_campaigns_table(df: pd.DataFrame, styles: dict) -> Table:
    rows = [["Campanha", "Custo por resultados", "Valor investido", "Alcance", "Impressões", "Cliques", "CPC", "CPM", "Frequência"]]
    for _, row in df.iterrows():
        cpm = _safe_div(float(row["Investimento"]) * 1000, float(row["Impressões"]))
        rows.append(
            [
                Paragraph(_escape(_clip(str(row["Campanha"]), 38)), styles["TableCell"]),
                Paragraph(f"{_money(float(row['Custo por Mensagem']))}<br/>Mensagem", styles["TableCellRight"]),
                _money(float(row["Investimento"])),
                _integer(float(row["Alcance"])),
                _integer(float(row["Impressões"])),
                _integer(float(row["Cliques"])),
                _money(float(row["CPC"])),
                _money(cpm),
                _ratio(float(row["Frequência"])),
            ]
        )
    table = Table(rows, colWidths=[50 * mm, 31 * mm, 28 * mm, 25 * mm, 25 * mm, 19 * mm, 18 * mm, 18 * mm, 22 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_PANEL),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 6.8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BRAND_SOFT]),
                ("GRID", (0, 0), (-1, -1), 0.25, BRAND_LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _fallback_pdf_story(df: pd.DataFrame, period: str, styles: dict) -> list:
    if df.empty:
        return [
            *_pdf_header(styles, period),
            Paragraph("Nenhum dado encontrado para os filtros selecionados.", styles["Empty"]),
        ]

    campaign_summary = _aggregate(df, ["Plataforma", "Conta", "Modelo da Campanha", "Campanha"]).sort_values(by="Investimento", ascending=False)
    totals = _totals(df)
    story = [
        *_pdf_header(styles, period),
        _kpi_cards(totals, styles),
        Spacer(1, 10),
        Paragraph("Resumo consolidado dos resultados", styles["SectionTitle"]),
        _actions_table(df, styles),
        Spacer(1, 10),
        Paragraph("Campanhas em destaque", styles["SectionTitle"]),
        _featured_campaigns_table(campaign_summary.head(10), styles),
        Spacer(1, 8),
        Paragraph(
            "Observação: o relatório usou a versão segura de exportação para preservar o download com todos os principais indicadores.",
            styles["BodyMuted"],
        ),
    ]
    return story


def _plain_table(rows: list[list], widths: list[float], styles: dict) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_PANEL),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BRAND_SOFT]),
                ("GRID", (0, 0), (-1, -1), 0.25, BRAND_LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


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
    base.add(ParagraphStyle("KpiValueLarge", parent=base["Normal"], textColor=BRAND_DARK, fontSize=15.5, leading=18, fontName="Helvetica-Bold"))
    base.add(ParagraphStyle("KpiDelta", parent=base["Normal"], textColor=BRAND_GREEN, fontSize=9, leading=11, fontName="Helvetica-Bold"))
    base.add(ParagraphStyle("KpiNote", parent=base["Normal"], textColor=BRAND_MUTED, fontSize=7.2, leading=9))
    base.add(ParagraphStyle("KpiCard", parent=base["Normal"], textColor=BRAND_DARK, fontSize=8, leading=10.8))
    base.add(ParagraphStyle("SmallLabel", parent=base["Normal"], textColor=BRAND_MUTED, fontSize=6.8, leading=8, fontName="Helvetica-Bold"))
    base.add(ParagraphStyle("SmallValue", parent=base["Normal"], textColor=BRAND_DARK, fontSize=9.4, leading=11, fontName="Helvetica-Bold"))
    base.add(ParagraphStyle("TableHeader", parent=base["Normal"], textColor=colors.white, fontSize=7.2, leading=8.5, fontName="Helvetica-Bold"))
    base.add(ParagraphStyle("TableCell", parent=base["Normal"], textColor=colors.HexColor("#1D2933"), fontSize=7.1, leading=8.5))
    base.add(ParagraphStyle("TableCellRight", parent=base["Normal"], textColor=colors.HexColor("#1D2933"), fontSize=7.1, leading=8.5, alignment=TA_RIGHT))
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


def _delta(current: float, previous: float) -> str:
    if not previous:
        return "Novo período"
    change = ((float(current) - float(previous)) / abs(float(previous))) * 100
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.2f}%".replace(".", ",")


def _format_metric(column: str, value: float) -> str:
    if column in {"Investimento", "CPC", "Custo por Mensagem", "Custo/Conv."}:
        return _money(float(value))
    if column in {"CTR (%)"}:
        return _percent(float(value))
    if column in {"Frequência", "ROAS"}:
        return _ratio(float(value))
    if column in {"Alcance", "Impressões", "Cliques"}:
        return _integer(float(value))
    if column in {"Mensagens", "Conversões"}:
        return _number(float(value))
    return str(value)


def _clip(value: str, max_length: int) -> str:
    clean = " ".join(str(value).split())
    return clean if len(clean) <= max_length else clean[: max_length - 1].rstrip() + "…"


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

from datetime import date, datetime
from io import BytesIO

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import CampaignMetric


def rows_to_dataframe(rows: list[CampaignMetric]) -> pd.DataFrame:
    data = [
        {
            "Data": row.date.isoformat(),
            "Plataforma": row.platform,
            "Conta": row.account_id,
            "Campanha": row.campaign_name,
            "Impressoes": row.impressions,
            "Cliques": row.clicks,
            "CTR (%)": row.ctr,
            "CPC": row.cpc,
            "Investimento": row.spend,
            "Conversoes": row.conversions,
            "Custo/Conv.": row.cost_per_conversion,
            "Valor Conv.": row.conversion_value,
            "ROAS": row.roas,
        }
        for row in rows
    ]
    return pd.DataFrame(data)


def build_excel(rows: list[CampaignMetric]) -> bytes:
    df = rows_to_dataframe(rows)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Historico")
        if not df.empty:
            summary = df.groupby("Plataforma", as_index=False).agg(
                {
                    "Impressoes": "sum",
                    "Cliques": "sum",
                    "Investimento": "sum",
                    "Conversoes": "sum",
                    "Valor Conv.": "sum",
                }
            )
            summary["CTR (%)"] = (summary["Cliques"] / summary["Impressoes"]).fillna(0) * 100
            summary["CPC"] = (summary["Investimento"] / summary["Cliques"]).fillna(0)
            summary["Custo/Conv."] = (summary["Investimento"] / summary["Conversoes"]).fillna(0)
            summary["ROAS"] = (summary["Valor Conv."] / summary["Investimento"]).fillna(0)
            summary.to_excel(writer, index=False, sheet_name="Resumo")
    return output.getvalue()


def build_pdf(rows: list[CampaignMetric], start_date: date | None = None, end_date: date | None = None) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=24, leftMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Relatorio consolidado de trafego pago", styles["Title"]),
        Paragraph(f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Normal"]),
        Spacer(1, 12),
    ]
    df = rows_to_dataframe(rows)
    if df.empty:
        story.append(Paragraph("Nenhum dado encontrado para os filtros selecionados.", styles["Normal"]))
    else:
        spend_total = float(df["Investimento"].sum())
        conversions_total = float(df["Conversoes"].sum())
        conversion_value_total = float(df["Valor Conv."].sum())
        average_roas = conversion_value_total / spend_total if spend_total else 0.0
        period = (
            f"{start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}"
            if start_date and end_date
            else "Periodo selecionado"
        )
        summary_data = [
            ["Periodo", "Investimento total", "Conversoes totais", "ROAS medio"],
            [period, _money(spend_total), f"{conversions_total:.2f}", f"{average_roas:.2f}"],
        ]
        summary_table = Table(summary_data, repeatRows=1)
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12171d")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d8dee6")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f7f9fb")),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ]
            )
        )
        story.append(summary_table)
        story.append(Spacer(1, 14))

        totals = df.groupby("Plataforma", as_index=False).agg(
            {
                "Impressoes": "sum",
                "Cliques": "sum",
                "Investimento": "sum",
                "Conversoes": "sum",
                "Valor Conv.": "sum",
            }
        )
        totals["CTR (%)"] = ((totals["Cliques"] / totals["Impressoes"]).fillna(0) * 100).round(2)
        totals["CPC"] = (totals["Investimento"] / totals["Cliques"]).fillna(0).round(2)
        totals["Custo/Conv."] = (totals["Investimento"] / totals["Conversoes"]).fillna(0).round(2)
        totals["ROAS"] = (totals["Valor Conv."] / totals["Investimento"]).fillna(0).round(2)
        columns = ["Plataforma", "Impressoes", "Cliques", "Investimento", "Conversoes", "CTR (%)", "CPC", "Custo/Conv.", "ROAS"]
        table_data = [columns] + totals[columns].astype(str).values.tolist()
        table = Table(table_data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324d")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d8dee6")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fb")]),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 14))

        campaign = df.groupby(["Plataforma", "Conta", "Campanha"], as_index=False).agg(
            {
                "Impressoes": "sum",
                "Cliques": "sum",
                "Investimento": "sum",
                "Conversoes": "sum",
                "Valor Conv.": "sum",
            }
        )
        campaign["CTR (%)"] = ((campaign["Cliques"] / campaign["Impressoes"]).fillna(0) * 100).round(2)
        campaign["CPC"] = (campaign["Investimento"] / campaign["Cliques"]).fillna(0).round(2)
        campaign["Custo/Conv."] = (campaign["Investimento"] / campaign["Conversoes"]).fillna(0).round(2)
        campaign["ROAS"] = (campaign["Valor Conv."] / campaign["Investimento"]).fillna(0).round(2)
        campaign["Investimento"] = campaign["Investimento"].map(_money)
        detail_columns = ["Plataforma", "Conta", "Campanha", "Impressoes", "Cliques", "Investimento", "Conversoes", "Custo/Conv.", "ROAS"]
        detail_table = Table([detail_columns] + campaign[detail_columns].astype(str).values.tolist(), repeatRows=1)
        detail_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324d")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d8dee6")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fb")]),
                    ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                ]
            )
        )
        story.append(Paragraph("Detalhamento por campanha", styles["Heading2"]))
        story.append(detail_table)
    document.build(story)
    return output.getvalue()


def _money(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

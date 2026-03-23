import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()

def get_api_key():
    try:
        import streamlit as st
        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        return os.getenv("ANTHROPIC_API_KEY")

import anthropic
client = anthropic.Anthropic(api_key=get_api_key())

def parse_csv(filepath):
    df = pd.read_csv(filepath)

    data = {
        "revenue_current": float(df["revenue_current"][0]),
        "revenue_1m_ago": float(df["revenue_1m_ago"][0]),
        "revenue_3m_ago": float(df["revenue_3m_ago"][0]),
        "expenses_current": float(df["expenses_current"][0]),
        "expenses_3m_ago": float(df["expenses_3m_ago"][0]),
        "cash_balance": float(df["cash_balance"][0]),
        "top_client_revenue": float(df["top_client_revenue"][0]),
        "accounts_receivable": float(df["accounts_receivable"][0]),
        "num_employees": float(df["num_employees"][0]),
        "gross_margin_current": float(df["gross_margin_current"][0]),
        "gross_margin_3m_ago": float(df["gross_margin_3m_ago"][0]),
    }
    return data


def _xero_parse_number(raw):
    """Convert a Xero-formatted cell to float.

    Handles:
      - commas as thousands separators: "12,345.67" -> 12345.67
      - parentheses for negatives:      "(1,234.56)" -> -1234.56
      - dashes / blanks for zero:       "-" or "" -> 0.0
    """
    if raw is None:
        return 0.0
    s = str(raw).strip()
    if s in ("", "-", "—"):
        return 0.0
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    try:
        value = float(s.replace(",", ""))
        return -value if negative else value
    except ValueError:
        return 0.0


def parse_xero_csv(filepath):
    """Parse a real Xero Profit & Loss CSV export.

    Xero P&L structure
    ------------------
    Row 0-N  : metadata (company name, report title, date range)
    Header   : first row where ≥2 cells match "Mon YYYY" (e.g. "Jan 2026")
    Data rows: label in col 0, values in month columns

    Returns the same dict shape as parse_csv().
    Fields that cannot be derived from a P&L (cash balance, top client
    revenue, accounts receivable, num employees) are returned as None
    so the caller can prompt the user to supply them manually.
    """
    import csv
    import re
    from datetime import datetime

    MONTH_RE = re.compile(
        r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}$",
        re.IGNORECASE,
    )

    with open(filepath, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    # ------------------------------------------------------------------
    # 1. Locate the header row and all month columns
    # ------------------------------------------------------------------
    header_idx = None
    month_cols = []  # [(col_index, datetime), ...]

    for i, row in enumerate(rows):
        found = []
        for j, cell in enumerate(row):
            if MONTH_RE.match(cell.strip()):
                try:
                    found.append((j, datetime.strptime(cell.strip(), "%b %Y")))
                except ValueError:
                    pass
        if len(found) >= 2:
            header_idx = i
            month_cols = found
            break

    if header_idx is None:
        raise ValueError(
            "Could not find month columns in the CSV. "
            "Expected headers like 'Jan 2026', 'Feb 2026'."
        )

    # Sort chronologically; keep the last 3
    month_cols.sort(key=lambda x: x[1])
    last3 = month_cols[-3:]

    col_current = last3[-1][0]
    col_1m_ago  = last3[-2][0] if len(last3) >= 2 else None
    col_3m_ago  = last3[0][0]

    # ------------------------------------------------------------------
    # 2. Index data rows by their normalised label
    # ------------------------------------------------------------------
    label_index = {}  # normalised_label -> row list
    for row in rows[header_idx + 1:]:
        if not row:
            continue
        label = row[0].strip().lower()
        if label and label not in label_index:
            label_index[label] = row

    def _get(keywords, col):
        """Return the numeric value for the first matching keyword at col."""
        if col is None:
            return None
        for kw in keywords:
            row = label_index.get(kw.lower())
            if row is not None and col < len(row):
                return _xero_parse_number(row[col])
        return None

    # ------------------------------------------------------------------
    # 3. Extract revenue
    # Xero typically totals income as "Total [Income/Revenue/Trading Income]"
    # ------------------------------------------------------------------
    REVENUE_KW = [
        "total revenue",
        "total operating revenue",
        "total income",
        "total trading income",
        "revenue",
        "income",
    ]
    rev_current = _get(REVENUE_KW, col_current)
    rev_1m_ago  = _get(REVENUE_KW, col_1m_ago)
    rev_3m_ago  = _get(REVENUE_KW, col_3m_ago)

    # ------------------------------------------------------------------
    # 4. Extract expenses
    # Total expenses = Cost of Sales + Operating Expenses.
    # Try a single "Total Expenses" row first; fall back to summing parts.
    # ------------------------------------------------------------------
    COGS_KW = [
        "total cost of sales",
        "cost of sales",
        "total direct costs",
        "direct costs",
        "total cost of goods sold",
        "cost of goods sold",
    ]
    OPEX_KW = [
        "total operating expenses",
        "operating expenses",
        "total overhead expenses",
        "overhead expenses",
        "total expenses",
        "expenses",
    ]

    def _total_expenses(col):
        single = _get(["total expenses", "total costs"], col)
        if single is not None:
            return single
        cogs = _get(COGS_KW, col) or 0.0
        opex = _get(OPEX_KW, col) or 0.0
        return (cogs + opex) if (cogs or opex) else None

    exp_current = _total_expenses(col_current)
    exp_3m_ago  = _total_expenses(col_3m_ago)

    # ------------------------------------------------------------------
    # 5. Gross margin = Gross Profit / Revenue
    # ------------------------------------------------------------------
    GP_KW = ["gross profit", "total gross profit"]

    def _gross_margin(col):
        gp  = _get(GP_KW, col)
        rev = _get(REVENUE_KW, col)
        if gp is not None and rev:
            return gp / rev
        return None

    gm_current = _gross_margin(col_current)
    gm_3m_ago  = _gross_margin(col_3m_ago)

    # ------------------------------------------------------------------
    # 6. Return in parse_csv() dict format
    # ------------------------------------------------------------------
    return {
        "revenue_current":      rev_current,
        "revenue_1m_ago":       rev_1m_ago,
        "revenue_3m_ago":       rev_3m_ago,
        "expenses_current":     exp_current,
        "expenses_3m_ago":      exp_3m_ago,
        "cash_balance":         None,
        "top_client_revenue":   None,
        "accounts_receivable":  None,
        "num_employees":        None,
        "gross_margin_current": gm_current,
        "gross_margin_3m_ago":  gm_3m_ago,
    }
def calculate_ratios(data):
    revenue_concentration = data["top_client_revenue"] / data["revenue_current"]
    
    dso = (data["accounts_receivable"] / data["revenue_current"]) * 30
    
    cash_runway = data["cash_balance"] / data["expenses_current"]
    
    gross_margin_trend = data["gross_margin_current"] - data["gross_margin_3m_ago"]
    
    expense_growth = (data["expenses_current"] - data["expenses_3m_ago"]) / data["expenses_3m_ago"]
    revenue_growth = (data["revenue_current"] - data["revenue_3m_ago"]) / data["revenue_3m_ago"]
    exp_vs_rev = expense_growth - revenue_growth
    
    annual_revenue = ((data["revenue_current"] + data["revenue_1m_ago"] + data["revenue_3m_ago"]) / 3) * 12
    rev_per_employee = annual_revenue / data["num_employees"]
    
    return {
        "revenue_concentration": revenue_concentration,
        "dso": dso,
        "cash_runway": cash_runway,
        "gross_margin_current": data["gross_margin_current"],
        "gross_margin_trend": gross_margin_trend,
        "exp_vs_rev": exp_vs_rev,
        "rev_per_employee": rev_per_employee,
    }
def score_revenue_concentration(value):
    if value < 0.25: return 10
    elif value < 0.35: return 7
    elif value < 0.45: return 5
    elif value < 0.60: return 3
    else: return 0

def score_dso(value):
    if value < 30: return 10
    elif value < 38: return 7
    elif value < 48: return 5
    elif value < 60: return 3
    else: return 0

def score_cash_runway(value):
    if value > 6: return 10
    elif value > 4.5: return 7
    elif value > 3: return 5
    elif value > 1.5: return 3
    else: return 0

def score_gross_margin(gm_current, gm_trend):
    if gm_current >= 0.45 and gm_trend >= -0.01: return 10
    elif gm_current >= 0.35 and gm_trend >= -0.01: return 7
    elif (gm_current >= 0.35 and gm_trend < -0.01) or (gm_current >= 0.25 and gm_trend >= -0.01): return 5
    elif (gm_current < 0.35 and gm_trend < -0.01) or (gm_current < 0.25 and gm_trend >= -0.01): return 3
    else: return 0

def score_exp_vs_rev(value):
    if value < -0.05: return 10
    elif value < -0.02: return 7
    elif value < 0.01: return 5
    elif value < 0.05: return 3
    else: return 0

def score_rev_per_employee(value):
    if value > 80000: return 10
    elif value > 65000: return 7
    elif value > 50000: return 5
    elif value > 35000: return 3
    else: return 0

def calculate_composite_score(ratios):
    scores = {
        "revenue_concentration": score_revenue_concentration(ratios["revenue_concentration"]),
        "dso": score_dso(ratios["dso"]),
        "cash_runway": score_cash_runway(ratios["cash_runway"]),
        "gross_margin": score_gross_margin(ratios["gross_margin_current"], ratios["gross_margin_trend"]),
        "exp_vs_rev": score_exp_vs_rev(ratios["exp_vs_rev"]),
        "rev_per_employee": score_rev_per_employee(ratios["rev_per_employee"]),
    }

    weights = {
        "revenue_concentration": 0.28,
        "dso": 0.22,
        "cash_runway": 0.20,
        "gross_margin": 0.15,
        "exp_vs_rev": 0.10,
        "rev_per_employee": 0.05,
    }

    composite = sum(scores[k] * weights[k] for k in scores) * 10
    return round(composite, 1), scores

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm

def get_ai_interpretation(business_name, score, scores, ratios):
    prompt = f"""You are a financial advisor giving plain-language feedback to a digital agency owner who has no accounting background.

Here is their Financial Health Score report:

Business: {business_name}
Composite Score: {score}/100

Ratio scores:
- Revenue Concentration: {scores['revenue_concentration']}/10 (top client = {ratios['revenue_concentration']*100:.1f}% of revenue)
- Days Sales Outstanding: {scores['dso']}/10 ({ratios['dso']:.1f} days average to get paid)
- Cash Runway: {scores['cash_runway']}/10 ({ratios['cash_runway']:.1f} months of cash remaining)
- Gross Margin: {scores['gross_margin']}/10 (current margin = {ratios['gross_margin_current']*100:.1f}%)
- Expense vs Revenue Growth: {scores['exp_vs_rev']}/10 (expense growth minus revenue growth = {ratios['exp_vs_rev']*100:.1f}%)
- Revenue per Employee: {scores['rev_per_employee']}/10 (€{ratios['rev_per_employee']:,.0f} per person annually)

Write exactly 3 key findings and exactly 2 recommended actions.

Format your response exactly like this:
FINDING 1: [what the number shows, why it matters for their agency, what happens if ignored]
FINDING 2: [what the number shows, why it matters for their agency, what happens if ignored]
FINDING 3: [what the number shows, why it matters for their agency, what happens if ignored]
ACTION 1: [specific, achievable action with a clear deadline]
ACTION 2: [specific, achievable action with a clear deadline]

Rules:
- No jargon. Write like a knowledgeable friend, not an accountant.
- Be specific — reference their actual numbers, not generic advice.
- Be honest — if something is dangerous, say so clearly.
- Each finding under 60 words.
- Each action under 40 words.
- Focus on the lowest-scoring ratios first."""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    response = message.content[0].text
    
    findings = []
    actions = []
    
    for line in response.strip().split('\n'):
        line = line.strip()
        if line.startswith('FINDING'):
            findings.append(line.split(':', 1)[1].strip())
        elif line.startswith('ACTION'):
            actions.append(line.split(':', 1)[1].strip())
    
    return findings, actions

def generate_pdf(business_name, score, scores, ratios, findings=None, actions=None, output_path="report.pdf"):
    doc = SimpleDocTemplate(output_path, pagesize=A4,
                           rightMargin=20*mm, leftMargin=20*mm,
                           topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle('title', fontSize=24, fontName='Helvetica-Bold',
                                  spaceAfter=6, textColor=colors.HexColor('#1A1A2E'))
    sub_style = ParagraphStyle('sub', fontSize=11, fontName='Helvetica',
                                spaceAfter=20, textColor=colors.HexColor('#666666'))
    section_style = ParagraphStyle('section', fontSize=13, fontName='Helvetica-Bold',
                                    spaceAfter=8, textColor=colors.HexColor('#2C3E7A'),
                                    spaceBefore=16)
    body_style = ParagraphStyle('body', fontSize=10, fontName='Helvetica',
                                 spaceAfter=6, textColor=colors.HexColor('#333333'),
                                 leading=15)

    story.append(Paragraph("ScoreMyAgency — Financial Health Report", title_style))
    story.append(Paragraph(business_name, sub_style))

    if score >= 70:
        score_color = colors.HexColor('#2E7D32')
        verdict = "Healthy"
    elif score >= 40:
        score_color = colors.HexColor('#E65100')
        verdict = "Struggling"
    else:
        score_color = colors.HexColor('#C62828')
        verdict = "Critical"

    score_data = [[f"{score} / 100", verdict]]
    score_table = Table(score_data, colWidths=[80*mm, 80*mm])
    score_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (0,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (0,0), 36),
        ('TEXTCOLOR', (0,0), (0,0), score_color),
        ('FONTNAME', (1,0), (1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (1,0), (1,0), 18),
        ('TEXTCOLOR', (1,0), (1,0), score_color),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
        ('TOPPADDING', (0,0), (-1,-1), 12),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F5F7FF')),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 12))

    story.append(Paragraph("Ratio Breakdown", section_style))
    ratio_labels = {
        "revenue_concentration": "Revenue Concentration",
        "dso": "Days Sales Outstanding",
        "cash_runway": "Cash Runway",
        "gross_margin": "Gross Margin",
        "exp_vs_rev": "Expense vs Revenue Growth",
        "rev_per_employee": "Revenue per Employee",
    }
    raw_values = {
        "revenue_concentration": f"{ratios['revenue_concentration']*100:.1f}%",
        "dso": f"{ratios['dso']:.1f} days",
        "cash_runway": f"{ratios['cash_runway']:.1f} months",
        "gross_margin": f"{ratios['gross_margin_current']*100:.1f}%",
        "exp_vs_rev": f"{ratios['exp_vs_rev']*100:.1f}%",
        "rev_per_employee": f"EUR {ratios['rev_per_employee']:,.0f}",
    }
    ratio_data = [["Ratio", "Score", "Raw Value"]]
    for key, label in ratio_labels.items():
        ratio_data.append([label, f"{scores[key]}/10", raw_values[key]])

    ratio_table = Table(ratio_data, colWidths=[90*mm, 30*mm, 50*mm])
    ratio_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2C3E7A')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F5F7FF')]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CCCCCC')),
        ('TOPPADDING', (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(ratio_table)

    story.append(Paragraph("Key Findings", section_style))
    findings = findings or ["No findings generated."]
    for f in findings:
        story.append(Paragraph(f"• {f}", body_style))

    story.append(Paragraph("Recommended Actions", section_style))
    actions = actions or ["No actions generated."]
    for a in actions:
        story.append(Paragraph(f"-> {a}", body_style))

    doc.build(story)
    print(f"Report saved to {output_path}")

if __name__ == "__main__":
    data = parse_csv("test_business.csv")
    ratios = calculate_ratios(data)
    score, scores = calculate_composite_score(ratios)
    
    print(f"\n--- FINANCIAL HEALTH SCORE ---")
    print(f"Composite Score: {score} / 100")
    print(f"\nIndividual Scores:")
    for k, v in scores.items():
        print(f"  {k}: {v}/10")
    
    print(f"\nGenerating AI interpretation...")
    findings, actions = get_ai_interpretation("Mosaic Digital", score, scores, ratios)
    
    print(f"\nFindings:")
    for f in findings:
        print(f"  - {f}")
    print(f"\nActions:")
    for a in actions:
        print(f"  - {a}")
    
    generate_pdf("Mosaic Digital", score, scores, ratios, findings, actions)
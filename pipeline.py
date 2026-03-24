import pandas as pd
import os
import sqlite3
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

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmarks.db")

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


# ---------------------------------------------------------------------------
# Benchmarking database
# ---------------------------------------------------------------------------

def _init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agency_benchmarks (
                id                        INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                agency_size               TEXT,
                revenue_concentration     REAL,
                dso                       REAL,
                cash_runway               REAL,
                gross_margin              REAL,
                expense_vs_revenue_growth REAL,
                revenue_per_employee      REAL,
                composite_score           REAL
            )
        """)
        conn.commit()


def _agency_size(num_employees):
    if num_employees <= 10:
        return "small"
    elif num_employees <= 30:
        return "medium"
    return "large"


def save_benchmark(data, ratios, composite_score):
    """Insert an anonymised benchmark row for this agency's analysis."""
    _init_db()
    size = _agency_size(data["num_employees"])
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO agency_benchmarks
                (agency_size, revenue_concentration, dso, cash_runway,
                 gross_margin, expense_vs_revenue_growth, revenue_per_employee, composite_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            size,
            ratios["revenue_concentration"],
            ratios["dso"],
            ratios["cash_runway"],
            ratios["gross_margin_current"],
            ratios["exp_vs_rev"],
            ratios["rev_per_employee"],
            composite_score,
        ))
        conn.commit()


def get_percentiles(agency_size, ratios):
    """Return a dict of percentile ranks (0-100) for each ratio.

    Higher percentile = better performance for that metric.
    Falls back to all sizes if fewer than 5 entries exist for the given size.
    """
    _init_db()
    with sqlite3.connect(DB_PATH) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM agency_benchmarks WHERE agency_size = ?", (agency_size,)
        ).fetchone()[0]
        where  = "agency_size = ?" if count >= 5 else "1=1"
        params = (agency_size,)      if count >= 5 else ()
        rows = conn.execute(
            f"SELECT revenue_concentration, dso, cash_runway, gross_margin, "
            f"expense_vs_revenue_growth, revenue_per_employee "
            f"FROM agency_benchmarks WHERE {where}",
            params,
        ).fetchall()

    if not rows:
        return {k: 50 for k in
                ["revenue_concentration", "dso", "cash_runway",
                 "gross_margin", "exp_vs_rev", "rev_per_employee"]}

    def pct(values, agency_val, higher_is_better):
        n = len(values)
        worse = sum(1 for v in values if (v < agency_val if higher_is_better else v > agency_val))
        return round(worse / n * 100)

    cols = list(zip(*rows))
    return {
        "revenue_concentration": pct(cols[0], ratios["revenue_concentration"], higher_is_better=False),
        "dso":                   pct(cols[1], ratios["dso"],                   higher_is_better=False),
        "cash_runway":           pct(cols[2], ratios["cash_runway"],           higher_is_better=True),
        "gross_margin":          pct(cols[3], ratios["gross_margin_current"],  higher_is_better=True),
        "exp_vs_rev":            pct(cols[4], ratios["exp_vs_rev"],            higher_is_better=False),
        "rev_per_employee":      pct(cols[5], ratios["rev_per_employee"],      higher_is_better=True),
    }


from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm

def get_ai_interpretation(business_name, score, scores, ratios):
    system = """You are a financial advisor specialising in digital agencies. You give plain-language feedback to agency owners who have no accounting background.

Agency benchmarks you must use when interpreting the numbers:
- Gross Margin: weak = below 50%, healthy = 50–70%, strong = 70%+
- Days Sales Outstanding (DSO): healthy = under 30 days, concerning = 30–45 days, dangerous = 45+ days
- Revenue Concentration: safe = under 25%, risky = 25–40%, dangerous = 40%+
- Cash Runway: critical = under 1 month, thin = 1–3 months, healthy = 3–6 months, strong = 6+ months
- Revenue per Employee: underperforming = below €60,000/year, healthy = €70,000–€120,000/year, strong = above €120,000/year
- Expense vs Revenue Growth: expenses growing faster than revenue is a warning sign at any level

Output rules:
- No jargon. Write like a knowledgeable friend, not an accountant.
- Be specific — reference their actual numbers and compare them to the benchmarks above.
- Be honest — if something is dangerous, say so clearly.
- Focus on the lowest-scoring ratios first.
- Each finding must be under 100 words.
- Each action must be under 60 words.

Format your response exactly like this, with no extra text before or after:
RISK SUMMARY: [one sentence — the single most important takeaway, like a doctor's top-line diagnosis]
FINDING 1: [what the number shows, how it compares to the benchmark, why it matters, what happens if ignored]
FINDING 2: [what the number shows, how it compares to the benchmark, why it matters, what happens if ignored]
FINDING 3: [what the number shows, how it compares to the benchmark, why it matters, what happens if ignored]
ACTION 1: [specific, achievable action with a clear deadline]
ACTION 2: [specific, achievable action with a clear deadline]"""

    user_message = f"""Here is the Financial Health Score report for {business_name}:

Composite Score: {score}/100

Ratio scores:
- Revenue Concentration: {scores['revenue_concentration']}/10 (top client = {ratios['revenue_concentration']*100:.1f}% of revenue)
- Days Sales Outstanding: {scores['dso']}/10 ({ratios['dso']:.1f} days average to get paid)
- Cash Runway: {scores['cash_runway']}/10 ({ratios['cash_runway']:.1f} months of cash remaining)
- Gross Margin: {scores['gross_margin']}/10 (current margin = {ratios['gross_margin_current']*100:.1f}%)
- Expense vs Revenue Growth: {scores['exp_vs_rev']}/10 (expense growth minus revenue growth = {ratios['exp_vs_rev']*100:.1f}%)
- Revenue per Employee: {scores['rev_per_employee']}/10 (€{ratios['rev_per_employee']:,.0f} per person annually)

Write the risk summary, 3 findings, and 2 actions."""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1500,
        system=system,
        messages=[{"role": "user", "content": user_message}]
    )

    response = message.content[0].text

    risk_summary = ""
    findings = []
    actions = []

    for line in response.strip().split('\n'):
        line = line.strip()
        if line.startswith('RISK SUMMARY:'):
            risk_summary = line.split(':', 1)[1].strip()
        elif line.startswith('FINDING'):
            findings.append(line.split(':', 1)[1].strip())
        elif line.startswith('ACTION'):
            actions.append(line.split(':', 1)[1].strip())

    return {"risk_summary": risk_summary, "findings": findings, "actions": actions}

def generate_pdf(business_name, score, scores, ratios, findings=None, actions=None, risk_summary=None, percentiles=None, output_path="report.pdf"):
    from datetime import date

    PAGE_W, _ = A4
    MARGIN    = 15 * mm
    CW        = PAGE_W - 2 * MARGIN  # usable content width = 180mm

    # Palette
    NAVY      = colors.HexColor('#1a2332')
    GREEN     = colors.HexColor('#22c55e')
    AMBER     = colors.HexColor('#f59e0b')
    RED       = colors.HexColor('#ef4444')
    SLATE     = colors.HexColor('#f1f5f9')
    RULE      = colors.HexColor('#e2e8f0')
    MUTED     = colors.HexColor('#6b7280')

    if score >= 70:
        score_hex, verdict = '#22c55e', 'Healthy'
    elif score >= 40:
        score_hex, verdict = '#f59e0b', 'Struggling'
    else:
        score_hex, verdict = '#ef4444', 'Critical'

    def ratio_hex(s):
        if s >= 7: return '#22c55e'
        if s >= 4: return '#f59e0b'
        return '#ef4444'

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        rightMargin=MARGIN, leftMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
    )

    # Base styles
    normal   = ParagraphStyle('pdf_normal',   fontSize=9,  fontName='Helvetica',
                               textColor=colors.HexColor('#1f2937'), leading=13)
    bold9    = ParagraphStyle('pdf_bold9',    fontSize=9,  fontName='Helvetica-Bold',
                               textColor=colors.HexColor('#1f2937'), leading=13)
    section  = ParagraphStyle('pdf_section',  fontSize=10, fontName='Helvetica-Bold',
                               textColor=NAVY, spaceBefore=8, spaceAfter=3)
    white9   = ParagraphStyle('pdf_white9',   fontSize=9,  fontName='Helvetica',
                               textColor=colors.white, leading=13)
    footer_s = ParagraphStyle('pdf_footer',   fontSize=7,  fontName='Helvetica',
                               textColor=MUTED, alignment=1)
    action_n = ParagraphStyle('pdf_action_n', fontSize=12, fontName='Helvetica-Bold',
                               textColor=NAVY, alignment=1, leading=14)

    today = date.today().strftime("%d %B %Y")
    story = []

    # -----------------------------------------------------------------------
    # 1. HEADER BAR
    # -----------------------------------------------------------------------
    hdr = Table(
        [[Paragraph('<font color="white" size="13"><b>ScoreMyAgency</b></font>', white9),
          Paragraph(f'<font color="#94a3b8" size="8">Financial Health Report</font>', white9)]],
        colWidths=[CW * 0.55, CW * 0.45],
    )
    hdr.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), NAVY),
        ('TOPPADDING',    (0,0), (-1,-1), 9),
        ('BOTTOMPADDING', (0,0), (-1,-1), 9),
        ('LEFTPADDING',   (0,0), (0,0),   12),
        ('RIGHTPADDING',  (-1,0), (-1,0), 12),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN',         (1,0), (1,0),   'RIGHT'),
    ]))
    story.append(hdr)

    sub = Table(
        [[Paragraph(f'<b>{business_name}</b>', bold9),
          Paragraph(f'<font color="#6b7280" size="8">Generated {today}</font>', normal)]],
        colWidths=[CW * 0.55, CW * 0.45],
    )
    sub.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), SLATE),
        ('TOPPADDING',    (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING',   (0,0), (0,0),   12),
        ('RIGHTPADDING',  (-1,0), (-1,0), 12),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN',         (1,0), (1,0),   'RIGHT'),
    ]))
    story.append(sub)
    story.append(Spacer(1, 8))

    # -----------------------------------------------------------------------
    # 2. SCORE + RISK SUMMARY
    # -----------------------------------------------------------------------
    diag = f'<i>{risk_summary}</i>' if risk_summary else ''
    score_cell = Paragraph(
        f'<font size="40" color="{score_hex}"><b>{score}</b></font>'
        f'<font size="13" color="{score_hex}"> /100</font>',
        normal,
    )
    verdict_cell = Paragraph(
        f'<font size="18" color="{score_hex}"><b>{verdict}</b></font>'
        + (f'<br/><br/><font size="8.5" color="#374151">{diag}</font>' if diag else ''),
        normal,
    )
    score_tbl = Table([[score_cell, verdict_cell]], colWidths=[CW * 0.25, CW * 0.75])
    score_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('TOPPADDING',    (0,0), (-1,-1), 11),
        ('BOTTOMPADDING', (0,0), (-1,-1), 11),
        ('LEFTPADDING',   (0,0), (0,0),   12),
        ('LEFTPADDING',   (1,0), (1,0),   10),
        ('RIGHTPADDING',  (-1,0), (-1,0), 12),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('LINEBELOW',     (0,0), (-1,-1), 2, colors.HexColor(score_hex)),
    ]))
    story.append(score_tbl)
    story.append(Spacer(1, 10))

    # -----------------------------------------------------------------------
    # 3. RATIO TABLE  (dot | name | score | value | benchmark)
    # -----------------------------------------------------------------------
    story.append(Paragraph("Ratio Breakdown", section))

    benchmarks = {
        "revenue_concentration": "Under 25%",
        "dso":                   "Under 30 days",
        "cash_runway":           "3–6 months",
        "gross_margin":          "50–70%",
        "exp_vs_rev":            "Expenses \u2264 Revenue growth",
        "rev_per_employee":      "\u20ac70k\u2013\u20ac120k / year",
    }
    ratio_labels = {
        "revenue_concentration": "Revenue Concentration",
        "dso":                   "Days Sales Outstanding",
        "cash_runway":           "Cash Runway",
        "gross_margin":          "Gross Margin",
        "exp_vs_rev":            "Expense vs Revenue Growth",
        "rev_per_employee":      "Revenue per Employee",
    }
    raw_values = {
        "revenue_concentration": f"{ratios['revenue_concentration']*100:.1f}%",
        "dso":                   f"{ratios['dso']:.1f} days",
        "cash_runway":           f"{ratios['cash_runway']:.1f} months",
        "gross_margin":          f"{ratios['gross_margin_current']*100:.1f}%",
        "exp_vs_rev":            f"{ratios['exp_vs_rev']*100:.1f}%",
        "rev_per_employee":      f"\u20ac{ratios['rev_per_employee']:,.0f}",
    }

    DOT_W = 6*mm;  NAME_W = 64*mm;  SCR_W = 18*mm;  VAL_W = 34*mm
    BMK_W = CW - DOT_W - NAME_W - SCR_W - VAL_W

    th = ParagraphStyle('pdf_th', fontSize=8, fontName='Helvetica-Bold', textColor=colors.white, leading=11)
    td = ParagraphStyle('pdf_td', fontSize=8, fontName='Helvetica',      textColor=colors.HexColor('#1f2937'), leading=11)
    tm = ParagraphStyle('pdf_tm', fontSize=8, fontName='Helvetica',      textColor=MUTED, leading=11)

    rows = [[Paragraph('', th), Paragraph('Ratio', th), Paragraph('Score', th),
             Paragraph('Your Value', th), Paragraph('Benchmark', th)]]
    cmds = [
        ('BACKGROUND',    (0,0), (-1,0), NAVY),
        ('TOPPADDING',    (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING',   (0,0), (-1,-1), 5),
        ('RIGHTPADDING',  (0,0), (-1,-1), 5),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('GRID',          (0,0), (-1,-1), 0.25, RULE),
    ]
    for i, (key, label) in enumerate(ratio_labels.items(), start=1):
        s    = scores[key]
        shex = ratio_hex(s)
        pct_text = (f'<br/><font size="6.5" color="#6b7280">top {percentiles[key]}%</font>'
                    if percentiles and key in percentiles else "")
        rows.append([
            '',   # background-colored cell used as indicator dot
            Paragraph(label, td),
            Paragraph(f'<font color="{shex}"><b>{s}/10</b></font>{pct_text}', td),
            Paragraph(raw_values[key], td),
            Paragraph(benchmarks[key], tm),
        ])
        cmds.append(('BACKGROUND', (0,i), (0,i), colors.HexColor(shex)))
        if i % 2 == 0:
            cmds.append(('BACKGROUND', (1,i), (-1,i), colors.HexColor('#f8f9fa')))

    ratio_tbl = Table(rows, colWidths=[DOT_W, NAME_W, SCR_W, VAL_W, BMK_W])
    ratio_tbl.setStyle(TableStyle(cmds))
    story.append(ratio_tbl)
    story.append(Spacer(1, 10))

    # -----------------------------------------------------------------------
    # 4. FINDINGS  (colored left-border sidebar)
    # -----------------------------------------------------------------------
    story.append(Paragraph("Key Findings", section))
    findings = findings or ["No findings generated."]
    finding_colors = ['#ef4444', '#f59e0b', '#6b7280']

    finding_rows = []
    for i, text in enumerate(findings):
        fc   = finding_colors[i] if i < len(finding_colors) else '#6b7280'
        cell = Paragraph(f'<b>{i+1}.</b>  {text}', normal)
        row  = Table([['', cell]], colWidths=[4*mm, CW - 4*mm])
        row.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (0,0),   colors.HexColor(fc)),
            ('BACKGROUND',    (1,0), (1,0),   colors.HexColor('#fafafa')),
            ('TOPPADDING',    (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING',   (0,0), (0,0),   0),
            ('RIGHTPADDING',  (0,0), (0,0),   0),
            ('LEFTPADDING',   (1,0), (1,0),   8),
            ('RIGHTPADDING',  (1,0), (1,0),   8),
            ('VALIGN',        (0,0), (-1,-1), 'TOP'),
            ('LINEBELOW',     (0,0), (-1,-1), 0.25, RULE),
        ]))
        finding_rows.append(row)

    story.append(KeepTogether(finding_rows))
    story.append(Spacer(1, 10))

    # -----------------------------------------------------------------------
    # 5. ACTIONS  (numbered, light-blue box)
    # -----------------------------------------------------------------------
    story.append(Paragraph("Recommended Actions", section))
    actions = actions or ["No actions generated."]

    for i, text in enumerate(actions):
        act = Table(
            [[Paragraph(str(i + 1), action_n), Paragraph(text, normal)]],
            colWidths=[10*mm, CW - 10*mm],
        )
        act.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,-1), colors.HexColor('#eff6ff')),
            ('TOPPADDING',    (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('LEFTPADDING',   (0,0), (0,0),   0),
            ('RIGHTPADDING',  (0,0), (0,0),   0),
            ('LEFTPADDING',   (1,0), (1,0),   10),
            ('RIGHTPADDING',  (1,0), (1,0),   10),
            ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
            ('LINEBEFORE',    (0,0), (0,-1),  3,    NAVY),
            ('LINEAFTER',     (0,0), (0,-1),  0.5,  RULE),
        ]))
        story.append(act)
        story.append(Spacer(1, 4))

    # -----------------------------------------------------------------------
    # 6. FOOTER
    # -----------------------------------------------------------------------
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width=CW, thickness=0.5, color=RULE))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f'Generated by ScoreMyAgency.com \u00b7 {today} \u00b7 '
        f'<font color="#9ca3af">CONFIDENTIAL</font>',
        footer_s,
    ))

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
    ai = get_ai_interpretation("Mosaic Digital", score, scores, ratios)

    print(f"\nRisk Summary: {ai['risk_summary']}")
    print(f"\nFindings:")
    for f in ai["findings"]:
        print(f"  - {f}")
    print(f"\nActions:")
    for a in ai["actions"]:
        print(f"  - {a}")

    generate_pdf("Mosaic Digital", score, scores, ratios, ai["findings"], ai["actions"], risk_summary=ai["risk_summary"])
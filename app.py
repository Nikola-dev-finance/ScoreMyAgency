import streamlit as st
import tempfile
import os
from pipeline import parse_csv, calculate_ratios, calculate_composite_score, get_ai_interpretation, generate_pdf

st.set_page_config(page_title="ScoreMyAgency", page_icon="📊", layout="centered")

st.title("📊 ScoreMyAgency")
st.markdown("Find out if your agency's finances are healthy — in 60 seconds.")

business_name = st.text_input("Agency name", placeholder="e.g. Mosaic Digital")


def run_and_display(business_name, data):
    ratios = calculate_ratios(data)
    score, scores = calculate_composite_score(ratios)

    with st.spinner("Generating AI interpretation..."):
        findings, actions = get_ai_interpretation(business_name, score, scores, ratios)

    # --- Score display ---
    if score >= 70:
        colour, verdict, bg = "#2E7D32", "Healthy",    "#E8F5E9"
    elif score >= 40:
        colour, verdict, bg = "#E65100", "Struggling", "#FFF3E0"
    else:
        colour, verdict, bg = "#C62828", "Critical",   "#FFEBEE"

    st.markdown(
        f"""
        <div style="background:{bg}; border-radius:12px; padding:24px 32px; margin:16px 0; display:flex; align-items:center; gap:32px;">
            <span style="font-size:56px; font-weight:800; color:{colour};">{score}</span>
            <div>
                <div style="font-size:13px; color:#666; font-weight:500; letter-spacing:1px; text-transform:uppercase;">Financial Health Score</div>
                <div style="font-size:24px; font-weight:700; color:{colour};">{verdict}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Ratio breakdown ---
    st.subheader("Ratio Breakdown")

    ratio_labels = {
        "revenue_concentration": ("Revenue Concentration",    f"{ratios['revenue_concentration']*100:.1f}%"),
        "dso":                   ("Days Sales Outstanding",   f"{ratios['dso']:.1f} days"),
        "cash_runway":           ("Cash Runway",              f"{ratios['cash_runway']:.1f} months"),
        "gross_margin":          ("Gross Margin",             f"{ratios['gross_margin_current']*100:.1f}%"),
        "exp_vs_rev":            ("Expense vs Revenue Growth",f"{ratios['exp_vs_rev']*100:.1f}%"),
        "rev_per_employee":      ("Revenue per Employee",     f"€{ratios['rev_per_employee']:,.0f}"),
    }

    cols = st.columns([3, 1, 2])
    cols[0].markdown("**Ratio**")
    cols[1].markdown("**Score**")
    cols[2].markdown("**Value**")
    st.divider()

    for key, (label, value) in ratio_labels.items():
        raw_score = scores[key]
        score_colour = "#2E7D32" if raw_score >= 7 else "#E65100" if raw_score >= 5 else "#C62828"
        cols = st.columns([3, 1, 2])
        cols[0].write(label)
        cols[1].markdown(f"<span style='color:{score_colour}; font-weight:700;'>{raw_score}/10</span>", unsafe_allow_html=True)
        cols[2].write(value)

    # --- Findings ---
    st.subheader("Key Findings")
    for i, finding in enumerate(findings, 1):
        st.info(f"**Finding {i}:** {finding}")

    # --- Actions ---
    st.subheader("Recommended Actions")
    for i, action in enumerate(actions, 1):
        st.success(f"**Action {i}:** {action}")

    # --- PDF download ---
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
        tmp_pdf_path = tmp_pdf.name
    try:
        generate_pdf(business_name, score, scores, ratios, findings, actions, output_path=tmp_pdf_path)
        with open(tmp_pdf_path, "rb") as f:
            pdf_bytes = f.read()
        st.download_button(
            label="📥 Download PDF Report",
            data=pdf_bytes,
            file_name=f"ScoreMyAgency_{business_name.replace(' ', '_')}.pdf",
            mime="application/pdf",
            type="primary",
        )
    finally:
        if os.path.exists(tmp_pdf_path):
            os.unlink(tmp_pdf_path)


tab_csv, tab_manual = st.tabs(["Upload CSV", "Enter manually"])

# ---------------------------------------------------------------------------
# Tab 1 — CSV upload
# ---------------------------------------------------------------------------
with tab_csv:
    uploaded_file = st.file_uploader("Upload your CSV export from Xero or QuickBooks", type=["csv"])

    if uploaded_file and business_name:
        if st.button("Run Analysis", type="primary", key="btn_csv"):
            with st.spinner("Analysing your financials..."):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_csv:
                    tmp_csv.write(uploaded_file.read())
                    tmp_csv_path = tmp_csv.name
                try:
                    data = parse_csv(tmp_csv_path)
                    run_and_display(business_name, data)
                finally:
                    os.unlink(tmp_csv_path)
    elif uploaded_file and not business_name:
        st.warning("Enter a business name before running the analysis.")
    elif business_name and not uploaded_file:
        st.info("Upload a CSV file to continue.")

# ---------------------------------------------------------------------------
# Tab 2 — Manual entry
# ---------------------------------------------------------------------------
with tab_manual:
    st.markdown("#### Revenue (last 3 months)")
    col1, col2, col3 = st.columns(3)
    rev_current = col1.number_input("This month (€)",    min_value=0.0, step=100.0, placeholder="e.g. 42000", key="rev_current")
    rev_1m      = col2.number_input("Last month (€)",    min_value=0.0, step=100.0, placeholder="e.g. 38000", key="rev_1m")
    rev_3m      = col3.number_input("3 months ago (€)",  min_value=0.0, step=100.0, placeholder="e.g. 35000", key="rev_3m")

    st.markdown("#### Costs")
    col1, col2 = st.columns(2)
    exp_current = col1.number_input("This month's expenses (€)",   min_value=0.0, step=100.0, placeholder="e.g. 28000", key="exp_current")
    exp_3m      = col2.number_input("3 months ago expenses (€)",   min_value=0.0, step=100.0, placeholder="e.g. 25000", key="exp_3m")

    st.markdown("#### Cash & Clients")
    col1, col2, col3 = st.columns(3)
    cash        = col1.number_input("Cash balance (€)",                    min_value=0.0, step=100.0, placeholder="e.g. 85000",  key="cash")
    top_client  = col2.number_input("Largest client monthly billing (€)",  min_value=0.0, step=100.0, placeholder="e.g. 12000",  key="top_client")
    ar          = col3.number_input("Outstanding invoices / AR (€)",       min_value=0.0, step=100.0, placeholder="e.g. 18000",  key="ar")

    st.markdown("#### Team & Margins")
    col1, col2, col3 = st.columns(3)
    employees   = col1.number_input("Number of employees",       min_value=1.0, step=1.0,   placeholder="e.g. 8",   key="employees")
    gm_current  = col2.number_input("Gross margin this month (%)", min_value=0.0, max_value=100.0, step=0.1, placeholder="e.g. 52", key="gm_current")
    gm_3m       = col3.number_input("Gross margin 3 months ago (%)", min_value=0.0, max_value=100.0, step=0.1, placeholder="e.g. 48", key="gm_3m")

    if st.button("Run Analysis", type="primary", key="btn_manual"):
        if not business_name:
            st.warning("Enter a business name before running the analysis.")
        elif rev_current == 0 or exp_current == 0 or employees == 0:
            st.warning("Please fill in at least revenue, expenses, and number of employees.")
        else:
            data = {
                "revenue_current":    float(rev_current),
                "revenue_1m_ago":     float(rev_1m),
                "revenue_3m_ago":     float(rev_3m),
                "expenses_current":   float(exp_current),
                "expenses_3m_ago":    float(exp_3m),
                "cash_balance":       float(cash),
                "top_client_revenue": float(top_client),
                "accounts_receivable":float(ar),
                "num_employees":      float(employees),
                "gross_margin_current": gm_current / 100,
                "gross_margin_3m_ago":  gm_3m / 100,
            }
            with st.spinner("Analysing your financials..."):
                run_and_display(business_name, data)

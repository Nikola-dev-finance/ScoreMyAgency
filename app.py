import streamlit as st
import tempfile
import os
from pipeline import parse_csv, calculate_ratios, calculate_composite_score, get_ai_interpretation, generate_pdf

st.set_page_config(page_title="ScoreMyAgency", page_icon="📊", layout="centered")

st.title("📊 ScoreMyAgency")
st.markdown("Find out if your agency's finances are healthy — in 60 seconds.")

business_name = st.text_input("Agency name", placeholder="e.g. Mosaic Digital")

uploaded_file = st.file_uploader("Upload your CSV export from Xero or QuickBooks", type=["csv"])

if uploaded_file and business_name:
    if st.button("Run Analysis", type="primary"):
        with st.spinner("Analysing your financials..."):
            # Save uploaded CSV to a temp file so parse_csv can read it
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp_csv:
                tmp_csv.write(uploaded_file.read())
                tmp_csv_path = tmp_csv.name

            try:
                data = parse_csv(tmp_csv_path)
                ratios = calculate_ratios(data)
                score, scores = calculate_composite_score(ratios)

                with st.spinner("Generating AI interpretation..."):
                    findings, actions = get_ai_interpretation(business_name, score, scores, ratios)

                # --- Score display ---
                if score >= 70:
                    colour = "#2E7D32"
                    verdict = "Healthy"
                    bg = "#E8F5E9"
                elif score >= 40:
                    colour = "#E65100"
                    verdict = "Struggling"
                    bg = "#FFF3E0"
                else:
                    colour = "#C62828"
                    verdict = "Critical"
                    bg = "#FFEBEE"

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
                    "revenue_concentration": ("Revenue Concentration", f"{ratios['revenue_concentration']*100:.1f}%"),
                    "dso":                   ("Days Sales Outstanding",  f"{ratios['dso']:.1f} days"),
                    "cash_runway":           ("Cash Runway",             f"{ratios['cash_runway']:.1f} months"),
                    "gross_margin":          ("Gross Margin",            f"{ratios['gross_margin_current']*100:.1f}%"),
                    "exp_vs_rev":            ("Expense vs Revenue Growth", f"{ratios['exp_vs_rev']*100:.1f}%"),
                    "rev_per_employee":      ("Revenue per Employee",    f"€{ratios['rev_per_employee']:,.0f}"),
                }

                cols = st.columns([3, 1, 2])
                cols[0].markdown("**Ratio**")
                cols[1].markdown("**Score**")
                cols[2].markdown("**Value**")
                st.divider()

                for key, (label, value) in ratio_labels.items():
                    raw_score = scores[key]
                    if raw_score >= 7:
                        score_colour = "#2E7D32"
                    elif raw_score >= 5:
                        score_colour = "#E65100"
                    else:
                        score_colour = "#C62828"

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

                # --- PDF generation and download ---
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                    tmp_pdf_path = tmp_pdf.name

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
                os.unlink(tmp_csv_path)
                if 'tmp_pdf_path' in locals() and os.path.exists(tmp_pdf_path):
                    os.unlink(tmp_pdf_path)

elif uploaded_file and not business_name:
    st.warning("Enter a business name before running the analysis.")
elif business_name and not uploaded_file:
    st.info("Upload a CSV file to continue.")

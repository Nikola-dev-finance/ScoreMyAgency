import streamlit as st
import tempfile
import os
from pipeline import (parse_financial_csv, calculate_ratios,
                       calculate_composite_score, get_ai_interpretation, generate_pdf, save_benchmark,
                       get_percentiles, _init_db, seed_initial_benchmarks, save_waitlist_entry,
                       get_waitlist_entries)

st.set_page_config(
    page_title="ScoreMyAgency — Financial Health Score for Digital Agencies",
    layout="wide",
)

st.markdown(
    '<meta name="description" content="Free financial health scoring tool for digital agencies. '
    "Upload your Xero P&L or enter numbers manually. Get a 0-100 score, peer benchmarks, "
    'and AI-powered recommendations in under 2 minutes.">',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Global CSS — matches landing/index.html design system
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,300&display=swap');

/* ── Base ── */
html, body, .stApp, [class*="css"] {
    font-family: 'DM Sans', system-ui, sans-serif !important;
    color: #4a4540 !important;
}
.stApp {
    background-color: #f8f7f4 !important;
}
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="block-container"] {
    background-color: #f8f7f4 !important;
}

/* ── Headings ── */
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3,
h1, h2, h3 {
    font-family: 'Instrument Serif', Georgia, serif !important;
    color: #12100e !important;
}

/* ── Hide Streamlit chrome ── */
#MainMenu, footer { visibility: hidden; }

/* ── Buttons: teal primary ── */
.stButton > button,
.stDownloadButton > button,
.stFormSubmitButton > button {
    background: #0f766e !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 10px !important;
    font-family: 'DM Sans', system-ui, sans-serif !important;
    font-weight: 600 !important;
    transition: background 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease !important;
    box-shadow: 0 1px 3px rgba(15,118,110,0.25), inset 0 1px 0 rgba(255,255,255,0.1) !important;
}
.stButton > button:hover,
.stDownloadButton > button:hover,
.stFormSubmitButton > button:hover {
    background: #0a5e58 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(15,118,110,0.3) !important;
}
.stButton > button:active,
.stDownloadButton > button:active {
    transform: translateY(0) !important;
}

/* ── Back button (ghost style) ── */
.back-btn-wrap a {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 0.45rem 1.1rem;
    background: #ffffff;
    border: 1px solid #e4ddd5;
    border-radius: 10px;
    font-family: 'DM Sans', system-ui, sans-serif;
    font-size: 0.875rem;
    font-weight: 500;
    color: #4a4540 !important;
    text-decoration: none;
    transition: border-color 0.15s, box-shadow 0.15s;
}
.back-btn-wrap a:hover {
    border-color: #bbb5ae;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

/* ── Tabs ── */
[data-baseweb="tab"] {
    font-family: 'DM Sans', system-ui, sans-serif !important;
    font-weight: 500 !important;
    color: #9b9488 !important;
    background: transparent !important;
}
[aria-selected="true"][data-baseweb="tab"] {
    color: #12100e !important;
}
[data-baseweb="tab-highlight"] {
    background-color: #0f766e !important;
}
[data-baseweb="tab-border"] {
    background-color: #e4ddd5 !important;
}

/* ── Text & number inputs ── */
[data-baseweb="input"],
[data-baseweb="base-input"] {
    background-color: #ffffff !important;
    border-color: #e4ddd5 !important;
    border-radius: 10px !important;
    color: #12100e !important;
}
[data-baseweb="input"]:focus-within {
    border-color: #0f766e !important;
    box-shadow: 0 0 0 1px #0f766e !important;
}
[data-testid="stNumberInput"] > div {
    background-color: #ffffff !important;
    border-color: #e4ddd5 !important;
    border-radius: 10px !important;
}
[data-testid="stTextInput"] > div > div {
    background-color: #ffffff !important;
    border-color: #e4ddd5 !important;
    border-radius: 10px !important;
}
/* ── Input text color (prevents white-on-white) ── */
.stNumberInput input,
.stTextInput input,
input[type="number"],
input[type="text"],
textarea {
    color: #12100e !important;
    -webkit-text-fill-color: #12100e !important;
}

/* ── File uploader ── */
[data-testid="stFileUploadDropzone"] {
    background-color: #ffffff !important;
    border-color: #e4ddd5 !important;
    border-radius: 10px !important;
}
[data-testid="stFileUploadDropzone"]:hover {
    border-color: #0f766e !important;
}

/* ── Progress bars ── */
[data-testid="stProgress"] > div > div > div > div {
    background-color: #0f766e !important;
}

/* ── Metric cards ── */
[data-testid="stMetric"] {
    background: #ffffff !important;
    border: 1px solid #e4ddd5 !important;
    border-radius: 16px !important;
    padding: 16px !important;
}

/* ── Selectbox ── */
[data-baseweb="select"] > div {
    background-color: #ffffff !important;
    border-color: #e4ddd5 !important;
    border-radius: 10px !important;
}

/* ── Dividers ── */
hr { border-color: #e4ddd5 !important; }
</style>
""", unsafe_allow_html=True)

_init_db()
seed_initial_benchmarks()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_PL_MISSING  = {"cash_balance", "top_client_revenue", "accounts_receivable", "num_employees"}
_MANUAL_NOTE = "Not available from P&L — please enter manually."

_SAMPLE_DATA = {
    "revenue_current":      85000,
    "revenue_1m_ago":       80000,
    "revenue_3m_ago":       76000,
    "expenses_current":     52000,
    "expenses_3m_ago":      49000,
    "cash_balance":         280000,
    "top_client_revenue":   17000,
    "accounts_receivable":  55000,
    "num_employees":        10,
    "gross_margin_current": 0.61,
    "gross_margin_3m_ago":  0.59,
}
_SAMPLE_FINDINGS = [
    "Revenue concentration at 20% sits safely below the 25% warning level. Your largest client "
    "represents a manageable share of revenue — if they reduce spend, it's a setback, not a crisis.",
    "Days Sales Outstanding of 19 days is excellent, nearly 11 days better than the 30-day benchmark. "
    "Fast collections keep cash flowing and eliminate the need for invoice financing.",
    "Cash runway of 5.4 months sits in the healthy 3–6 month zone. You have a solid buffer for "
    "unexpected costs or a slow quarter, with enough headroom to invest in growth.",
]
_SAMPLE_ACTIONS = [
    "Keep no single client above 20% of revenue. When any client approaches 18%, immediately begin "
    "pitching two new prospects to maintain your diversification cushion.",
    "With 5.4 months of runway, you can afford one strategic investment now. Identify your single "
    "highest-ROI hire or marketing channel and commit to it within the next 60 days.",
]
_SAMPLE_RISK = (
    "Strong fundamentals across the board — your main job right now is investing this "
    "stability into growth before a competitor does."
)


# ---------------------------------------------------------------------------
# Sample PDF — built once per session, served from cache
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _build_sample_pdf(_cache_v: int = 2) -> bytes:  # bump _cache_v to force regeneration
    ratios = calculate_ratios(_SAMPLE_DATA)
    score, scores = calculate_composite_score(ratios)
    try:
        pcts = get_percentiles("small", ratios)
    except Exception:
        pcts = None
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        path = tmp.name
    try:
        generate_pdf(
            "Coastal Creative (Sample)", score, scores, ratios,
            _SAMPLE_FINDINGS, _SAMPLE_ACTIONS,
            risk_summary=_SAMPLE_RISK,
            percentiles=pcts,
            output_path=path,
        )
        with open(path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(path):
            os.unlink(path)


# ---------------------------------------------------------------------------
# Scoring pipeline — compute then render (split so results survive reruns)
# ---------------------------------------------------------------------------
def _compute_and_store(business_name, data):
    """Run the full analysis and persist every result in session state."""
    ratios = calculate_ratios(data)
    score, scores = calculate_composite_score(ratios)

    n = data["num_employees"]
    agency_size = "small" if n <= 10 else ("medium" if n <= 30 else "large")
    percentiles = get_percentiles(agency_size, ratios)
    save_benchmark(data, ratios, score)

    with st.spinner("Generating AI interpretation..."):
        ai = get_ai_interpretation(business_name, score, scores, ratios, percentiles=percentiles)

    risk_summary = ai["risk_summary"]
    findings     = ai["findings"]
    actions      = ai["actions"]

    # Generate PDF once and store the bytes so reruns don't regenerate it
    pdf_bytes = None
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
        tmp_path = tmp_pdf.name
    try:
        generate_pdf(business_name, score, scores, ratios, findings, actions,
                     risk_summary=risk_summary, percentiles=percentiles, output_path=tmp_path)
        with open(tmp_path, "rb") as f:
            pdf_bytes = f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    st.session_state["_results"] = {
        "business_name": business_name,
        "score":         score,
        "scores":        scores,
        "ratios":        ratios,
        "risk_summary":  risk_summary,
        "findings":      findings,
        "actions":       actions,
        "percentiles":   percentiles,
        "pdf_bytes":     pdf_bytes,
    }


def _render_results():
    """Render results stored by _compute_and_store. Safe to call on every rerun."""
    r = st.session_state["_results"]
    business_name = r["business_name"]
    score         = r["score"]
    scores        = r["scores"]
    ratios        = r["ratios"]
    risk_summary  = r["risk_summary"]
    findings      = r["findings"]
    actions       = r["actions"]
    percentiles   = r["percentiles"]
    pdf_bytes     = r["pdf_bytes"]

    # --- Score display ---
    if score >= 70:
        colour, verdict, bg = "#2E7D32", "Healthy",    "#E8F5E9"
    elif score >= 40:
        colour, verdict, bg = "#E65100", "Struggling", "#FFF3E0"
    else:
        colour, verdict, bg = "#C62828", "Critical",   "#FFEBEE"

    st.markdown(
        f"""
        <div style="background:{bg}; border-radius:12px; padding:24px 32px; margin:16px 0;
                    display:flex; align-items:center; gap:32px;">
            <span style="font-size:56px; font-weight:800; color:{colour};">{score}</span>
            <div>
                <div style="font-size:13px; color:#666; font-weight:500; letter-spacing:1px;
                            text-transform:uppercase;">Financial Health Score</div>
                <div style="font-size:24px; font-weight:700; color:{colour};">{verdict}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if risk_summary:
        st.markdown(
            f"<div style='background:#f1ede8; border-left:4px solid #0f766e; border-radius:8px; "
            f"padding:12px 16px; margin:8px 0; font-size:15px; color:#4a4540;'>"
            f"<strong>Diagnosis:</strong> {risk_summary}</div>",
            unsafe_allow_html=True,
        )

    st.subheader("Ratio Breakdown")

    ratio_labels = {
        "revenue_concentration": ("Revenue Concentration",     f"{ratios['revenue_concentration']*100:.1f}%"),
        "dso":                   ("Days Sales Outstanding",    f"{ratios['dso']:.1f} days"),
        "cash_runway":           ("Cash Runway",               f"{ratios['cash_runway']:.1f} months"),
        "gross_margin":          ("Gross Margin",              f"{ratios['gross_margin_current']*100:.1f}%"),
        "exp_vs_rev":            ("Expense vs Revenue Growth", f"{ratios['exp_vs_rev']*100:.1f}%"),
        "rev_per_employee":      ("Revenue per Employee",      f"€{ratios['rev_per_employee']:,.0f}"),
    }

    cols = st.columns([3, 1, 2, 2])
    cols[0].markdown("**Ratio**")
    cols[1].markdown("**Score**")
    cols[2].markdown("**Value**")
    cols[3].markdown("**Percentile**")
    st.divider()

    for key, (label, value) in ratio_labels.items():
        raw_score    = scores[key]
        score_colour = "#2E7D32" if raw_score >= 7 else "#E65100" if raw_score >= 5 else "#C62828"
        pct          = percentiles.get(key, 50)
        pct_colour   = "#2E7D32" if pct >= 60 else "#E65100" if pct >= 35 else "#C62828"
        cols = st.columns([3, 1, 2, 2])
        cols[0].write(label)
        cols[1].markdown(f"<span style='color:{score_colour}; font-weight:700;'>{raw_score}/10</span>", unsafe_allow_html=True)
        cols[2].write(value)
        cols[3].markdown(f"<span style='color:{pct_colour}; font-weight:600;'>Top {pct}%</span>", unsafe_allow_html=True)

    st.markdown(
        "<p style='font-size:11px; color:#9ca3af; margin:4px 0 16px;'>"
        "Based on agency benchmark data. Percentiles become more precise as more agencies use the tool.</p>",
        unsafe_allow_html=True,
    )

    st.subheader("Key Findings")
    for i, finding in enumerate(findings, 1):
        st.info(f"**Finding {i}:** {finding}")

    st.subheader("Recommended Actions")
    for i, action in enumerate(actions, 1):
        st.success(f"**Action {i}:** {action}")

    if pdf_bytes:
        st.download_button(
            label="📥 Download PDF Report",
            data=pdf_bytes,
            file_name=f"ScoreMyAgency_{business_name.replace(' ', '_')}.pdf",
            mime="application/pdf",
            type="primary",
        )

    # --- Email capture ---
    st.markdown("<div style='height:16px;'/>", unsafe_allow_html=True)
    st.markdown(
        "<div style='background:#ffffff; border:1px solid #e4ddd5; border-radius:16px; "
        "padding:20px 24px;'>",
        unsafe_allow_html=True,
    )
    st.markdown("**Want this report automatically every month?**")
    st.markdown(
        "<p style='color:#6b7280; font-size:13px; margin:-8px 0 12px;'>"
        "We'll email you an updated score each month so you can track your progress.</p>",
        unsafe_allow_html=True,
    )

    wl_key = f"wl_done_{business_name}"
    if st.session_state.get(wl_key):
        st.success("You're on the list! We'll be in touch.")
    else:
        wl_email = st.text_input(
            "Your email address",
            placeholder="you@youragency.com",
            key=f"wl_email_{business_name}",
            label_visibility="collapsed",
        )
        if st.button("Join waitlist", key=f"wl_btn_{business_name}"):
            if not wl_email or "@" not in wl_email:
                st.warning("Please enter a valid email address.")
            else:
                try:
                    save_waitlist_entry(wl_email, business_name, score)
                    st.session_state[wl_key] = True
                    # Safe to rerun — _results is already in session_state
                    st.rerun()
                except Exception as e:
                    st.error(f"Couldn't save your email: {e}")

    st.markdown(
        "<p style='font-size:12px; color:#9ca3af; margin-top:12px;'>"
        "Or fill out our form: "
        "<a href='https://docs.google.com/forms/d/e/1FAIpQLSdKQLLlH-mjLRfItqjdxFjjJX4YxZSjkBLZNyRRCP9_hef0aQ/viewform?usp=header' "
        "target='_blank' style='color:#6b7280;'>Google Form</a></p>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Landing page
# ---------------------------------------------------------------------------
def _show_landing_page():
    st.markdown("""
    <style>
    .step-card {
        background: #ffffff; border: 1px solid #e4ddd5;
        border-radius: 16px; padding: 28px 24px; text-align: center; height: 100%;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .step-card:hover {
        border-color: #0f766e;
        box-shadow: 0 4px 20px rgba(15, 118, 110, 0.1);
    }
    .step-num {
        display: inline-flex; align-items: center; justify-content: center;
        background: rgba(15,118,110,0.1); color: #0f766e;
        font-family: 'Instrument Serif', Georgia, serif;
        font-size: 15px; font-weight: 400; border-radius: 50%;
        width: 32px; height: 32px; margin-bottom: 14px;
    }
    .step-title {
        font-family: 'Instrument Serif', Georgia, serif;
        font-size: 16px; font-weight: 400; color: #12100e; margin: 0 0 8px;
    }
    .step-body  { font-size: 13px; color: #9b9488; line-height: 1.6; margin: 0; }
    .preview-card {
        background: #ffffff; border: 1px solid #e4ddd5;
        border-radius: 16px; padding: 20px 24px; margin-bottom: 8px;
    }
    .preview-score {
        display: flex; align-items: center; gap: 20px;
        background: #f0fdf9; border: 1px solid #ccfbf1;
        border-radius: 10px; padding: 16px 20px; margin-bottom: 12px;
    }
    .preview-ratio-row {
        display: flex; justify-content: space-between; align-items: center;
        padding: 6px 0; border-bottom: 1px solid #f1ede8; font-size: 13px;
    }
    .proof-stat {
        font-family: 'Instrument Serif', Georgia, serif;
        font-size: 2.2rem; font-weight: 400; color: #0f766e; margin-bottom: 4px;
    }
    .proof-label { font-size: 13px; color: #9b9488; }
    .divider-line {
        border: none; border-top: 1px solid #e4ddd5; margin: 40px 0;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Hero ──────────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="
        background: radial-gradient(ellipse 80% 60% at 50% -10%, rgba(15,118,110,0.08) 0%, transparent 60%),
                    #f8f7f4;
        border: 1px solid #e4ddd5;
        border-radius: 24px;
        padding: 80px 24px 68px;
        text-align: center;
        margin-bottom: 8px;
    ">
        <h1 style="
            font-family: 'Instrument Serif', Georgia, serif;
            font-size: 2.8rem; font-weight: 400; color: #12100e;
            line-height: 1.15; margin: 0 auto 20px; max-width: 700px;
        ">Know your agency's <em style="font-style:italic; color:#0f766e;">real financial health</em> in 2 minutes</h1>
        <p style="
            font-family: 'DM Sans', system-ui, sans-serif;
            font-size: 1.05rem; color: #9b9488; line-height: 1.75;
            max-width: 520px; margin: 0 auto 36px; font-weight: 300;
        ">Upload your Xero P&amp;L or enter your numbers manually. Get a score,
        peer benchmarks, and specific actions to improve — powered by AI.</p>
    </div>
    """, unsafe_allow_html=True)

    col_l, col_c, col_r = st.columns([1.5, 2, 1.5])
    with col_c:
        if st.button("Score My Agency →", type="primary", use_container_width=True):
            st.session_state.show_tool = True
            st.rerun()

    st.markdown("<hr class='divider-line'/>", unsafe_allow_html=True)

    # ── How it works ──────────────────────────────────────────────────────────
    st.markdown(
        "<h2 style='text-align:center; font-size:24px; font-weight:700; "
        "color:#12100e; margin-bottom:24px;'>How it works</h2>",
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("""
        <div class="step-card">
            <div class="step-num">1</div>
            <p class="step-title">Upload your data</p>
            <p class="step-body">Drop in your Xero Profit &amp; Loss CSV, or type your
            revenue, costs, cash balance, and headcount manually. Takes under 2 minutes.</p>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown("""
        <div class="step-card">
            <div class="step-num">2</div>
            <p class="step-title">Get your score</p>
            <p class="step-body">We calculate 6 key financial ratios and combine them into
            a single 0–100 score. See where you're healthy and where the risks are hiding.</p>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown("""
        <div class="step-card">
            <div class="step-num">3</div>
            <p class="step-title">See how you compare</p>
            <p class="step-body">Your ratios are benchmarked against 50+ real agency data
            points. AI identifies your top risks and gives you specific actions to fix them.</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<hr class='divider-line'/>", unsafe_allow_html=True)

    # ── Sample report ─────────────────────────────────────────────────────────
    st.markdown(
        "<h2 style='text-align:center; font-size:24px; font-weight:700; "
        "color:#12100e; margin-bottom:6px;'>See a sample report</h2>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align:center; color:#9b9488; font-size:14px; margin-bottom:24px;'>"
        "Here's what you get for a healthy agency. Download the full PDF below.</p>",
        unsafe_allow_html=True,
    )

    col_prev, col_dl = st.columns([3, 2])

    with col_prev:
        st.markdown("""
        <div class="preview-card">
            <div class="preview-score">
                <span style="font-size:44px; font-weight:800; color:#2E7D32;">90</span>
                <div>
                    <div style="font-size:11px; color:#666; font-weight:600;
                                letter-spacing:1px; text-transform:uppercase;">Financial Health Score</div>
                    <div style="font-size:18px; font-weight:700; color:#2E7D32;">Healthy &#10003;</div>
                </div>
            </div>
            <div style="font-size:12px; color:#4a4540; background:#f1ede8;
                        border-left:3px solid #0f766e; padding:8px 10px; border-radius:6px; margin-bottom:4px;">
                <strong>Diagnosis:</strong> Strong fundamentals across the board &#8212; focus on
                investing this stability into growth.
            </div>
        </div>
        """, unsafe_allow_html=True)

        pc1, pc2, pc3 = st.columns(3)
        with pc1:
            st.caption("Revenue Concentration")
            st.progress(1.0)
            st.markdown("**10/10** · 20.0% · Top 88%")
        with pc2:
            st.caption("Days Sales Outstanding")
            st.progress(1.0)
            st.markdown("**10/10** · 19.4 days · Top 77%")
        with pc3:
            st.caption("Cash Runway")
            st.progress(0.7)
            st.markdown("**7/10** · 5.4 months · Top 88%")

        st.caption("+ 3 more ratios, AI findings & actions in full report")

    with col_dl:
        st.markdown(
            "<div style='padding:16px 0;'>"
            "<p style='font-size:14px; color:#9b9488; margin-bottom:16px;'>"
            "Full report includes all 6 ratios, percentile benchmarks, AI-written findings, "
            "and action items — in a branded PDF.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        with st.spinner("Preparing sample..."):
            try:
                sample_bytes = _build_sample_pdf()
                st.download_button(
                    label="📄 Download Sample Report",
                    data=sample_bytes,
                    file_name="ScoreMyAgency_Sample_Report.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"Could not generate sample: {e}")

        st.markdown("<div style='margin-top:12px;'>", unsafe_allow_html=True)
        if st.button("Score My Agency →", type="primary",
                     use_container_width=True, key="cta_sample"):
            st.session_state.show_tool = True
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<hr class='divider-line'/>", unsafe_allow_html=True)

    # ── Social proof ──────────────────────────────────────────────────────────
    st.markdown(
        "<h2 style='text-align:center; font-size:24px; font-weight:700; "
        "color:#12100e; margin-bottom:24px;'>Built for digital agencies</h2>",
        unsafe_allow_html=True,
    )

    sp1, sp2, sp3 = st.columns(3)
    with sp1:
        st.markdown("""
        <div style="text-align:center; padding:20px 12px;">
            <div class="proof-stat">50+</div>
            <div class="proof-label" style="color:#9b9488; font-size:14px;">agency benchmarks from<br>industry research and public data</div>
        </div>
        """, unsafe_allow_html=True)
    with sp2:
        st.markdown("""
        <div style="text-align:center; padding:20px 12px;">
            <div class="proof-stat" style="color:#0f766e;">6</div>
            <div class="proof-label" style="color:#9b9488; font-size:14px;">financial ratios<br>tailored to agencies</div>
        </div>
        """, unsafe_allow_html=True)
    with sp3:
        st.markdown("""
        <div style="text-align:center; padding:20px 12px;">
            <div class="proof-stat" style="color:#0f766e;">&lt;2 min</div>
            <div class="proof-label" style="color:#9b9488; font-size:14px;">from data upload<br>to full AI report</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:48px;'/>", unsafe_allow_html=True)

    # Bottom CTA
    col_l2, col_c2, col_r2 = st.columns([1.5, 2, 1.5])
    with col_c2:
        if st.button("Score My Agency — it's free →",
                     type="primary", use_container_width=True, key="cta_bottom"):
            st.session_state.show_tool = True
            st.rerun()

    st.markdown("<div style='height:32px;'/>", unsafe_allow_html=True)

    # Footer
    st.divider()
    st.caption("ScoreMyAgency · Built by Nikola · Questions? hello@scoremyagency.com")


# ---------------------------------------------------------------------------
# Scoring tool
# ---------------------------------------------------------------------------
def _show_scoring_tool():
    # Back to home — link to external landing page if arrived via ?tool=true, else toggle session state
    if st.query_params.get("tool") == "true":
        # TODO: Change to https://scoremyagency.com when domain is live
        _back_url = "https://scoremyagency.streamlit.app"
        st.markdown(
            f"<div class='back-btn-wrap'><a href='{_back_url}'>← Back to home</a></div>",
            unsafe_allow_html=True,
        )
    else:
        if st.button("← Back to home", key="btn_back"):
            st.session_state.show_tool = False
            st.session_state.pop("_results", None)
            st.rerun()

    st.markdown(
        "<h1 style='font-family:\"Instrument Serif\",Georgia,serif; font-size:2rem; "
        "font-weight:400; color:#12100e; margin:12px 0 4px;'>"
        "Score<em style='font-style:italic; color:#0f766e;'>My</em>Agency</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='font-family:\"DM Sans\",system-ui,sans-serif; font-size:1rem; "
        "color:#9b9488; font-weight:300; margin:0 0 20px;'>"
        "Find out if your agency's finances are healthy — in 60 seconds.</p>",
        unsafe_allow_html=True,
    )

    business_name = st.text_input("Agency name", placeholder="e.g. Mosaic Digital")

    tab_manual, tab_csv = st.tabs(["Enter your numbers", "Upload Xero/QBO CSV"])

    # ── Tab 1: Xero CSV ───────────────────────────────────────────────────────
    with tab_csv:
        uploaded_file = st.file_uploader(
            "Upload a Profit & Loss CSV export from Xero or QuickBooks Online. We'll auto-detect the format.", type=["csv"]
        )
        st.caption("🔒 Your data is processed in real-time and never stored on our servers.")

        if uploaded_file:
            file_id = f"{uploaded_file.name}_{uploaded_file.size}"

            if st.session_state.get("_xero_file_id") != file_id:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = tmp.name
                try:
                    p = parse_financial_csv(tmp_path)
                    missing = {k for k, v in p.items() if v is None}
                    st.session_state.update({
                        "xr_rev_current":  p["revenue_current"]      or 0.0,
                        "xr_rev_1m":       p["revenue_1m_ago"]        or 0.0,
                        "xr_rev_3m":       p["revenue_3m_ago"]        or 0.0,
                        "xr_exp_current":  p["expenses_current"]      or 0.0,
                        "xr_exp_3m":       p["expenses_3m_ago"]       or 0.0,
                        "xr_cash":         0.0,
                        "xr_top_client":   0.0,
                        "xr_ar":           0.0,
                        "xr_employees":    1.0,
                        "xr_gm_current":   (p["gross_margin_current"] or 0.0) * 100,
                        "xr_gm_3m":        (p["gross_margin_3m_ago"]  or 0.0) * 100,
                    })
                    st.session_state["_xero_file_id"]   = file_id
                    st.session_state["_xero_missing"]   = missing
                    st.session_state["_xero_parse_err"] = None
                except Exception as exc:
                    st.session_state["_xero_file_id"]   = file_id
                    st.session_state["_xero_parse_err"] = str(exc)
                finally:
                    os.unlink(tmp_path)

            parse_err = st.session_state.get("_xero_parse_err")

            if parse_err:
                st.error(f"Could not parse this file: {parse_err}")
                st.info("Switch to the **Enter manually** tab to enter your figures directly.")

            elif st.session_state.get("_xero_file_id") == file_id:
                missing      = st.session_state.get("_xero_missing", set())
                needs_manual = missing & _PL_MISSING

                if needs_manual:
                    field_names = {
                        "cash_balance":        "Cash balance",
                        "top_client_revenue":  "Largest client billing",
                        "accounts_receivable": "Outstanding invoices",
                        "num_employees":       "Number of employees",
                    }
                    labels = ", ".join(field_names[k] for k in needs_manual if k in field_names)
                    st.warning(
                        f"P&L parsed. The following fields aren't in a P&L report — "
                        f"please fill them in below: **{labels}**"
                    )
                else:
                    st.success("P&L parsed successfully. Review the values below, then click Score.")

                st.markdown("#### Revenue (last 3 months)")
                col1, col2, col3 = st.columns(3)
                col1.number_input("This month (€)",   min_value=0.0, step=100.0, key="xr_rev_current")
                col2.number_input("Last month (€)",   min_value=0.0, step=100.0, key="xr_rev_1m")
                col3.number_input("3 months ago (€)", min_value=0.0, step=100.0, key="xr_rev_3m")

                st.markdown("#### Costs")
                col1, col2 = st.columns(2)
                col1.number_input("This month's expenses (€)", min_value=0.0, step=100.0, key="xr_exp_current")
                col2.number_input("3 months ago expenses (€)", min_value=0.0, step=100.0, key="xr_exp_3m")

                st.markdown("#### Cash & Clients")
                col1, col2, col3 = st.columns(3)
                col1.number_input("Cash balance (€)",                   min_value=0.0, step=100.0,
                                  key="xr_cash",       help=_MANUAL_NOTE)
                col2.number_input("Largest client monthly billing (€)", min_value=0.0, step=100.0,
                                  key="xr_top_client", help=_MANUAL_NOTE)
                col3.number_input("Outstanding invoices / AR (€)",      min_value=0.0, step=100.0,
                                  key="xr_ar",         help=_MANUAL_NOTE)

                st.markdown("#### Team & Margins")
                col1, col2, col3 = st.columns(3)
                col1.number_input("Number of employees",           min_value=1.0, step=1.0,
                                  key="xr_employees",  help=_MANUAL_NOTE)
                col2.number_input("Gross margin this month (%)",   min_value=0.0, max_value=100.0,
                                  step=0.1, key="xr_gm_current")
                col3.number_input("Gross margin 3 months ago (%)", min_value=0.0, max_value=100.0,
                                  step=0.1, key="xr_gm_3m")

                if not business_name:
                    st.warning("Enter a business name above before scoring.")
                elif st.button("Score", type="primary", key="btn_xero_score"):
                    ss = st.session_state
                    incomplete = []
                    if ss["xr_cash"]        == 0.0: incomplete.append("Cash balance")
                    if ss["xr_top_client"]  == 0.0: incomplete.append("Largest client billing")
                    if ss["xr_ar"]          == 0.0: incomplete.append("Outstanding invoices / AR")
                    if ss["xr_employees"]   <= 0.0: incomplete.append("Number of employees")
                    if ss["xr_rev_current"] == 0.0: incomplete.append("This month's revenue")
                    if ss["xr_exp_current"] == 0.0: incomplete.append("This month's expenses")

                    if incomplete:
                        st.warning(f"Please fill in: {', '.join(incomplete)}")
                    else:
                        data = {
                            "revenue_current":      float(ss["xr_rev_current"]),
                            "revenue_1m_ago":       float(ss["xr_rev_1m"]),
                            "revenue_3m_ago":       float(ss["xr_rev_3m"]),
                            "expenses_current":     float(ss["xr_exp_current"]),
                            "expenses_3m_ago":      float(ss["xr_exp_3m"]),
                            "cash_balance":         float(ss["xr_cash"]),
                            "top_client_revenue":   float(ss["xr_top_client"]),
                            "accounts_receivable":  float(ss["xr_ar"]),
                            "num_employees":        float(ss["xr_employees"]),
                            "gross_margin_current": ss["xr_gm_current"] / 100,
                            "gross_margin_3m_ago":  ss["xr_gm_3m"] / 100,
                        }
                        with st.spinner("Analysing your financials..."):
                            _compute_and_store(business_name, data)

        elif business_name:
            st.info("Upload a Xero P&L CSV to continue.")

    # ── Tab 2: Manual entry ───────────────────────────────────────────────────
    with tab_manual:
        st.caption("Takes about 60 seconds. You'll need: revenue for the last 3 months, total costs, largest client revenue, accounts receivable, cash balance, and headcount.")
        st.markdown("#### Revenue (last 3 months)")
        col1, col2, col3 = st.columns(3)
        rev_current = col1.number_input("This month (€)",    min_value=0.0, step=100.0, placeholder="e.g. 42000", key="rev_current")
        rev_1m      = col2.number_input("Last month (€)",    min_value=0.0, step=100.0, placeholder="e.g. 38000", key="rev_1m")
        rev_3m      = col3.number_input("3 months ago (€)",  min_value=0.0, step=100.0, placeholder="e.g. 35000", key="rev_3m")

        st.markdown("#### Costs")
        col1, col2 = st.columns(2)
        exp_current = col1.number_input("This month's expenses (€)", min_value=0.0, step=100.0, placeholder="e.g. 28000", key="exp_current")
        exp_3m      = col2.number_input("3 months ago expenses (€)", min_value=0.0, step=100.0, placeholder="e.g. 25000", key="exp_3m")

        st.markdown("#### Cash & Clients")
        col1, col2, col3 = st.columns(3)
        cash       = col1.number_input("Cash balance (€)",                   min_value=0.0, step=100.0, placeholder="e.g. 85000", key="cash")
        top_client = col2.number_input("Largest client monthly billing (€)", min_value=0.0, step=100.0, placeholder="e.g. 12000", key="top_client")
        ar         = col3.number_input("Outstanding invoices / AR (€)",      min_value=0.0, step=100.0, placeholder="e.g. 18000", key="ar")

        st.markdown("#### Team & Margins")
        col1, col2, col3 = st.columns(3)
        employees  = col1.number_input("Number of employees",           min_value=1.0, step=1.0, placeholder="e.g. 8",  key="employees")
        gm_current = col2.number_input("Gross margin this month (%)",   min_value=0.0, max_value=100.0, step=0.1, placeholder="e.g. 52", key="gm_current")
        gm_3m      = col3.number_input("Gross margin 3 months ago (%)", min_value=0.0, max_value=100.0, step=0.1, placeholder="e.g. 48", key="gm_3m")

        if st.button("Run Analysis", type="primary", key="btn_manual"):
            if not business_name:
                st.warning("Enter a business name before running the analysis.")
            elif rev_current == 0 or exp_current == 0 or employees == 0:
                st.warning("Please fill in at least revenue, expenses, and number of employees.")
            else:
                data = {
                    "revenue_current":      float(rev_current),
                    "revenue_1m_ago":       float(rev_1m),
                    "revenue_3m_ago":       float(rev_3m),
                    "expenses_current":     float(exp_current),
                    "expenses_3m_ago":      float(exp_3m),
                    "cash_balance":         float(cash),
                    "top_client_revenue":   float(top_client),
                    "accounts_receivable":  float(ar),
                    "num_employees":        float(employees),
                    "gross_margin_current": gm_current / 100,
                    "gross_margin_3m_ago":  gm_3m / 100,
                }
                with st.spinner("Analysing your financials..."):
                    _compute_and_store(business_name, data)

    # Render persisted results (survives any rerun including email submit)
    if "_results" in st.session_state:
        _render_results()


# ---------------------------------------------------------------------------
# Admin page
# ---------------------------------------------------------------------------
def _show_admin():
    st.title("Admin — Waitlist")
    entries = get_waitlist_entries()
    st.caption(f"{len(entries)} sign-up{'s' if len(entries) != 1 else ''} total")
    if not entries:
        st.info("No waitlist entries yet.")
        return
    st.dataframe(
        entries,
        column_config={
            "email":         st.column_config.TextColumn("Email"),
            "business_name": st.column_config.TextColumn("Agency"),
            "score":         st.column_config.NumberColumn("Score", format="%.1f"),
            "created_at":    st.column_config.TextColumn("Submitted (UTC)"),
        },
        use_container_width=True,
        hide_index=True,
    )


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
if st.query_params.get("admin") == "true":
    _show_admin()
elif st.query_params.get("tool") == "true" or st.session_state.get("show_tool", False):
    _show_scoring_tool()
else:
    _show_landing_page()

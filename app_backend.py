"""
Xero OAuth 2.0 backend for ScoreMyAgency.

Endpoints:
  GET  /xero/connect      — redirect user to Xero authorization page
  GET  /xero/callback     — exchange auth code for tokens, store in DB
  GET  /xero/pull-data    — pull financial reports, return pipeline-ready dict
"""

import os
import sqlite3
import time
import base64
import hashlib
import secrets as _secrets_mod
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, redirect, request, jsonify, session
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me-in-production")

# ---------------------------------------------------------------------------
# Config — set these in .env or Streamlit secrets
# ---------------------------------------------------------------------------
XERO_CLIENT_ID     = os.getenv("XERO_CLIENT_ID")
XERO_CLIENT_SECRET = os.getenv("XERO_CLIENT_SECRET")
XERO_REDIRECT_URI  = os.getenv("XERO_REDIRECT_URI", "http://localhost:5000/xero/callback")

XERO_AUTH_URL      = "https://login.xero.com/identity/connect/authorize"
XERO_TOKEN_URL     = "https://identity.xero.com/connect/token"
XERO_CONNECTIONS_URL = "https://api.xero.com/connections"
XERO_API_BASE      = "https://api.xero.com/api.xro/2.0"

SCOPES = "openid profile email offline_access accounting.reports.read accounting.invoices accounting.payments accounting.settings"

DB_PATH = os.getenv("TOKEN_DB_PATH", "xero_tokens.db")

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS xero_tokens (
                id            INTEGER PRIMARY KEY,
                tenant_id     TEXT NOT NULL,
                tenant_name   TEXT,
                access_token  TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at    REAL NOT NULL,
                updated_at    TEXT NOT NULL
            )
        """)
        conn.commit()


def save_tokens(tenant_id, tenant_name, access_token, refresh_token, expires_in):
    expires_at = time.time() + expires_in - 60  # 60-second buffer
    with _db() as conn:
        conn.execute("""
            INSERT INTO xero_tokens
                (tenant_id, tenant_name, access_token, refresh_token, expires_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                tenant_id     = excluded.tenant_id,
                tenant_name   = excluded.tenant_name,
                access_token  = excluded.access_token,
                refresh_token = excluded.refresh_token,
                expires_at    = excluded.expires_at,
                updated_at    = excluded.updated_at
        """, (tenant_id, tenant_name, access_token, refresh_token, expires_at,
              datetime.now(timezone.utc).isoformat()))
        conn.commit()


def load_tokens():
    """Return the most recently updated token row, or None."""
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM xero_tokens ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

def _basic_auth_header():
    creds = f"{XERO_CLIENT_ID}:{XERO_CLIENT_SECRET}"
    return "Basic " + base64.b64encode(creds.encode()).decode()


def refresh_access_token(tokens: dict) -> dict:
    resp = requests.post(
        XERO_TOKEN_URL,
        headers={
            "Authorization": _basic_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type":    "refresh_token",
            "refresh_token": tokens["refresh_token"],
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    save_tokens(
        tokens["tenant_id"],
        tokens["tenant_name"],
        data["access_token"],
        data["refresh_token"],
        data["expires_in"],
    )
    return data["access_token"]


def get_valid_access_token() -> tuple[str, str]:
    """Return (access_token, tenant_id), refreshing if needed."""
    tokens = load_tokens()
    if not tokens:
        raise RuntimeError("No Xero tokens stored. User must connect first.")

    if time.time() >= tokens["expires_at"]:
        access_token = refresh_access_token(tokens)
    else:
        access_token = tokens["access_token"]

    return access_token, tokens["tenant_id"]


# ---------------------------------------------------------------------------
# Xero API helpers
# ---------------------------------------------------------------------------

def _xero_get(path: str, params: dict | None = None) -> dict:
    access_token, tenant_id = get_valid_access_token()
    resp = requests.get(
        f"{XERO_API_BASE}/{path}",
        headers={
            "Authorization":  f"Bearer {access_token}",
            "Xero-Tenant-Id": tenant_id,
            "Accept":         "application/json",
        },
        params=params or {},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def _find_report_row(rows: list, title: str) -> float:
    """Walk Xero report rows to find a cell value by row title."""
    for row in rows:
        if row.get("RowType") == "Row":
            cells = row.get("Cells", [])
            if cells and cells[0].get("Value", "").strip().lower() == title.lower():
                # Return the first numeric value found
                for cell in cells[1:]:
                    try:
                        return float(cell.get("Value", 0) or 0)
                    except (ValueError, TypeError):
                        continue
        # Recurse into Section rows
        for sub in row.get("Rows", []):
            result = _find_report_row([sub], title)
            if result is not None:
                return result
    return None


def _safe(value) -> float:
    try:
        return float(value or 0)
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Xero report fetchers
# ---------------------------------------------------------------------------

def fetch_profit_and_loss(periods: int = 3) -> dict:
    """
    Returns a dict with keys:
      revenue_current, revenue_1m_ago, revenue_3m_ago,
      expenses_current, expenses_3m_ago,
      gross_margin_current, gross_margin_3m_ago
    """
    today = datetime.now(timezone.utc)
    from_date = (today - timedelta(days=90)).strftime("%Y-%m-%d")
    to_date   = today.strftime("%Y-%m-%d")

    data = _xero_get("Reports/ProfitAndLoss", {
        "fromDate":  from_date,
        "toDate":    to_date,
        "periods":   periods,
        "timeframe": "MONTH",
    })

    reports = data.get("Reports", [])
    if not reports:
        raise ValueError("Empty Profit & Loss response from Xero.")

    rows = reports[0].get("Rows", [])

    def find(title):
        return _safe(_find_report_row(rows, title))

    # Xero P&L column order: oldest → newest (left → right)
    # With periods=3 we get columns: [2m ago, 1m ago, current month]
    # We read each period by fetching per-month and picking the right cell.
    # Simpler: fetch with periods=3, parse the Section rows directly.

    # Build per-column revenue / expense / gross-profit extraction
    income_rows     = []
    expense_rows    = []
    gross_profit    = []

    for section in rows:
        title = section.get("Title", "")
        if "income" in title.lower() or "revenue" in title.lower() or "trading income" in title.lower():
            for row in section.get("Rows", []):
                if row.get("RowType") == "SummaryRow":
                    income_rows = [_safe(c.get("Value")) for c in row.get("Cells", [])[1:]]
        if "cost of sales" in title.lower() or "direct costs" in title.lower():
            pass  # not used directly — gross profit is captured below
        if "gross profit" in title.lower():
            for row in section.get("Rows", []):
                if row.get("RowType") in ("Row", "SummaryRow"):
                    cells = row.get("Cells", [])
                    if cells and "gross" in cells[0].get("Value", "").lower():
                        gross_profit = [_safe(c.get("Value")) for c in cells[1:]]
        if "operating expenses" in title.lower() or "expenses" in title.lower():
            for row in section.get("Rows", []):
                if row.get("RowType") == "SummaryRow":
                    expense_rows = [_safe(c.get("Value")) for c in row.get("Cells", [])[1:]]

    # Pad short lists so index access is safe
    def _col(lst, idx, default=0.0):
        return lst[idx] if len(lst) > idx else default

    rev_current  = _col(income_rows, -1)
    rev_1m_ago   = _col(income_rows, -2)
    rev_3m_ago   = _col(income_rows, 0)

    exp_current  = _col(expense_rows, -1)
    exp_3m_ago   = _col(expense_rows, 0)

    gp_current   = _col(gross_profit, -1)
    gp_3m_ago    = _col(gross_profit, 0)

    gm_current   = (gp_current / rev_current)  if rev_current  else 0.0
    gm_3m_ago    = (gp_3m_ago  / rev_3m_ago)   if rev_3m_ago   else 0.0

    return {
        "revenue_current":      rev_current,
        "revenue_1m_ago":       rev_1m_ago,
        "revenue_3m_ago":       rev_3m_ago,
        "expenses_current":     exp_current,
        "expenses_3m_ago":      exp_3m_ago,
        "gross_margin_current": gm_current,
        "gross_margin_3m_ago":  gm_3m_ago,
    }


def fetch_balance_sheet() -> dict:
    """Returns {"cash_balance": float}"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data  = _xero_get("Reports/BalanceSheet", {"date": today})

    reports = data.get("Reports", [])
    if not reports:
        raise ValueError("Empty Balance Sheet response from Xero.")

    rows = reports[0].get("Rows", [])
    cash = 0.0

    for section in rows:
        title = section.get("Title", "")
        if "current assets" in title.lower() or "bank" in title.lower():
            for row in section.get("Rows", []):
                label = ""
                if row.get("RowType") == "Row":
                    cells = row.get("Cells", [])
                    label = cells[0].get("Value", "").lower() if cells else ""
                if any(kw in label for kw in ("cash", "bank", "petty cash")):
                    cells = row.get("Cells", [])
                    for cell in cells[1:]:
                        try:
                            cash += float(cell.get("Value") or 0)
                        except (ValueError, TypeError):
                            pass

    return {"cash_balance": cash}


def fetch_aged_receivables() -> dict:
    """Returns {"accounts_receivable": float, "top_client_revenue": float}"""
    data = _xero_get("Reports/AgedReceivablesByContact")

    reports = data.get("Reports", [])
    if not reports:
        raise ValueError("Empty Aged Receivables response from Xero.")

    rows   = reports[0].get("Rows", [])
    totals = []

    for section in rows:
        for row in section.get("Rows", []) if isinstance(section, dict) else []:
            if row.get("RowType") == "Row":
                cells = row.get("Cells", [])
                # Last cell is typically the row total
                if len(cells) >= 2:
                    try:
                        totals.append(float(cells[-1].get("Value") or 0))
                    except (ValueError, TypeError):
                        pass

    accounts_receivable = sum(totals)
    top_client_revenue  = max(totals) if totals else 0.0

    return {
        "accounts_receivable": accounts_receivable,
        "top_client_revenue":  top_client_revenue,
    }


def fetch_employee_count() -> dict:
    """
    Xero Payroll (AU/NZ/UK) exposes employee count.
    For orgs without Payroll access this falls back to 1
    to avoid division-by-zero in the pipeline.
    """
    try:
        data  = _xero_get("Employees")
        count = len(data.get("Employees", []))
        return {"num_employees": float(max(count, 1))}
    except Exception:
        return {"num_employees": 1.0}


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@app.route("/debug")
def debug():
    client_id = XERO_CLIENT_ID or ""
    return jsonify({
        "XERO_CLIENT_ID":    (client_id[:10] + "...") if len(client_id) > 10 else ("<not set>" if not client_id else client_id),
        "XERO_REDIRECT_URI": XERO_REDIRECT_URI or "<not set>",
        "env_loaded":        bool(XERO_CLIENT_ID and XERO_REDIRECT_URI),
    })


@app.route("/xero/connect")
def xero_connect():
    """Redirect the user to Xero's OAuth 2.0 authorization page (PKCE flow)."""
    state = _secrets_mod.token_urlsafe(16)
    code_verifier = _secrets_mod.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    session["xero_state"] = state
    session["xero_code_verifier"] = code_verifier

    from urllib.parse import urlencode
    params = urlencode({
        "response_type":         "code",
        "client_id":             XERO_CLIENT_ID,
        "redirect_uri":          XERO_REDIRECT_URI,
        "scope":                 SCOPES,
        "state":                 state,
        "code_challenge":        code_challenge,
        "code_challenge_method": "S256",
    })
    auth_url = XERO_AUTH_URL + "?" + params
    print(f"[xero/connect] Authorization URL:\n{auth_url}\n")
    return redirect(auth_url)


@app.route("/xero/callback")
def xero_callback():
    """Exchange the authorization code for tokens and store them."""
    error = request.args.get("error")
    if error:
        return jsonify({"error": error, "description": request.args.get("error_description")}), 400

    # CSRF check
    returned_state = request.args.get("state", "")
    if returned_state != session.get("xero_state", ""):
        return jsonify({"error": "state_mismatch"}), 400

    code = request.args.get("code")
    if not code:
        return jsonify({"error": "no_code"}), 400

    # Exchange code for tokens
    code_verifier = session.get("xero_code_verifier")
    if not code_verifier:
        return jsonify({"error": "missing_code_verifier"}), 400

    resp = requests.post(
        XERO_TOKEN_URL,
        headers={
            "Authorization": _basic_auth_header(),
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        data={
            "grant_type":    "authorization_code",
            "code":          code,
            "redirect_uri":  XERO_REDIRECT_URI,
            "code_verifier": code_verifier,
        },
        timeout=15,
    )
    resp.raise_for_status()
    token_data = resp.json()

    # Resolve tenant (organisation) — pick the first one
    connections_resp = requests.get(
        XERO_CONNECTIONS_URL,
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
        timeout=10,
    )
    connections_resp.raise_for_status()
    connections = connections_resp.json()
    if not connections:
        return jsonify({"error": "no_tenants"}), 400

    tenant = connections[0]
    save_tokens(
        tenant_id     = tenant["tenantId"],
        tenant_name   = tenant.get("tenantName", ""),
        access_token  = token_data["access_token"],
        refresh_token = token_data["refresh_token"],
        expires_in    = token_data["expires_in"],
    )

    return jsonify({
        "status":      "connected",
        "tenant_name": tenant.get("tenantName", ""),
        "tenant_id":   tenant["tenantId"],
    })


@app.route("/xero/pull-data")
def xero_pull_data():
    """
    Pull financial data from Xero and return a dict that matches
    the shape of parse_csv() in pipeline.py.
    """
    try:
        pl   = fetch_profit_and_loss()
        bs   = fetch_balance_sheet()
        ar   = fetch_aged_receivables()
        emp  = fetch_employee_count()

        financial_data = {
            "revenue_current":      pl["revenue_current"],
            "revenue_1m_ago":       pl["revenue_1m_ago"],
            "revenue_3m_ago":       pl["revenue_3m_ago"],
            "expenses_current":     pl["expenses_current"],
            "expenses_3m_ago":      pl["expenses_3m_ago"],
            "cash_balance":         bs["cash_balance"],
            "top_client_revenue":   ar["top_client_revenue"],
            "accounts_receivable":  ar["accounts_receivable"],
            "num_employees":        emp["num_employees"],
            "gross_margin_current": pl["gross_margin_current"],
            "gross_margin_3m_ago":  pl["gross_margin_3m_ago"],
        }
        return jsonify(financial_data)

    except RuntimeError as e:
        return jsonify({"error": "not_connected", "detail": str(e)}), 401
    except requests.HTTPError as e:
        return jsonify({"error": "xero_api_error", "detail": str(e)}), 502
    except Exception as e:
        return jsonify({"error": "unexpected", "detail": str(e)}), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(port=5000, debug=True)

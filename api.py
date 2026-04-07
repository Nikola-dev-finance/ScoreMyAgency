import os
import tempfile

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from pipeline import (
    parse_financial_csv,
    calculate_ratios,
    calculate_composite_score,
    get_percentiles,
    get_ai_interpretation,
    generate_pdf,
    save_waitlist_entry,
    save_benchmark,
    _agency_size,
)

app = Flask(__name__)
CORS(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_scoring_pipeline(data, business_name):
    """Shared logic: ratios → composite score → percentiles → AI interpretation."""
    ratios = calculate_ratios(data)
    score, scores = calculate_composite_score(ratios)
    agency_size = _agency_size(data["num_employees"])

    try:
        save_benchmark(data, ratios, score)
    except Exception as exc:
        app.logger.warning("save_benchmark failed: %s", exc)

    percentiles = get_percentiles(agency_size, ratios)
    interpretation = get_ai_interpretation(business_name, score, scores, ratios, percentiles)

    return {
        "business_name": business_name,
        "score": score,
        "scores": scores,
        "ratios": ratios,
        "percentiles": percentiles,
        "risk_summary": interpretation["risk_summary"],
        "findings": interpretation["findings"],
        "actions": interpretation["actions"],
    }


def _require_json_fields(body, fields):
    missing = [f for f in fields if f not in body or body[f] is None]
    return missing


# ---------------------------------------------------------------------------
# POST /api/score
# ---------------------------------------------------------------------------

SCORE_FIELDS = [
    "revenue_current", "revenue_1m_ago", "revenue_3m_ago",
    "expenses_current", "expenses_3m_ago",
    "cash_balance", "top_client_revenue", "accounts_receivable",
    "num_employees", "gross_margin_current", "gross_margin_3m_ago",
]

@app.route("/api/score", methods=["POST"])
def score():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body must be JSON."}), 400

    missing = _require_json_fields(body, SCORE_FIELDS)
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    business_name = body.get("name") or "Your Agency"

    try:
        data = {field: float(body[field]) for field in SCORE_FIELDS}
    except (TypeError, ValueError) as exc:
        return jsonify({"error": f"All financial fields must be numeric. ({exc})"}), 400

    try:
        result = _run_scoring_pipeline(data, business_name)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        app.logger.exception("Scoring pipeline failed")
        return jsonify({"error": f"Scoring failed: {exc}"}), 500

    return jsonify(result)


# ---------------------------------------------------------------------------
# POST /api/upload-csv
# ---------------------------------------------------------------------------

@app.route("/api/upload-csv", methods=["POST"])
def upload_csv():
    if "file" not in request.files:
        return jsonify({"error": "No file part in request. Send a multipart field named 'file'."}), 400

    csv_file = request.files["file"]
    if csv_file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    business_name = request.form.get("name") or "Your Agency"

    # Fields that can't be derived from a P&L must be provided as form fields
    manual_fields = {}
    manual_keys = ["cash_balance", "top_client_revenue", "accounts_receivable", "num_employees"]
    for key in manual_keys:
        val = request.form.get(key)
        if val is not None:
            try:
                manual_fields[key] = float(val)
            except ValueError:
                return jsonify({"error": f"Field '{key}' must be numeric."}), 400

    suffix = os.path.splitext(csv_file.filename)[1] or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = tmp.name
        csv_file.save(tmp_path)

    try:
        data = parse_financial_csv(tmp_path)
    except Exception as exc:
        os.unlink(tmp_path)
        return jsonify({"error": f"Could not parse CSV: {exc}"}), 422
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # Merge in manually supplied fields; check for anything still missing
    data.update(manual_fields)
    missing = [k for k in manual_keys if data.get(k) is None]
    if missing:
        return jsonify({
            "error": (
                "The CSV does not contain all required fields. "
                f"Please also supply these as form fields: {', '.join(missing)}"
            ),
            "missing_fields": missing,
        }), 422

    # Ensure all numeric fields are floats
    for key in SCORE_FIELDS:
        if data.get(key) is None:
            return jsonify({"error": f"Could not derive '{key}' from the CSV."}), 422
        data[key] = float(data[key])

    try:
        result = _run_scoring_pipeline(data, business_name)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:
        app.logger.exception("Scoring pipeline failed")
        return jsonify({"error": f"Scoring failed: {exc}"}), 500

    return jsonify(result)


# ---------------------------------------------------------------------------
# POST /api/generate-pdf
# ---------------------------------------------------------------------------

@app.route("/api/generate-pdf", methods=["POST"])
def generate_pdf_endpoint():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body must be JSON."}), 400

    required = ["business_name", "score", "scores", "ratios"]
    missing = _require_json_fields(body, required)
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(tmp_fd)

    try:
        generate_pdf(
            business_name=body["business_name"],
            score=body["score"],
            scores=body["scores"],
            ratios=body["ratios"],
            findings=body.get("findings"),
            actions=body.get("actions"),
            risk_summary=body.get("risk_summary"),
            percentiles=body.get("percentiles"),
            output_path=tmp_path,
        )
    except Exception as exc:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        app.logger.exception("PDF generation failed")
        return jsonify({"error": f"PDF generation failed: {exc}"}), 500

    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in body["business_name"])
    download_name = f"{safe_name}_ScoreMyAgency.pdf"

    return send_file(
        tmp_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download_name,
    )


# ---------------------------------------------------------------------------
# POST /api/waitlist
# ---------------------------------------------------------------------------

@app.route("/api/waitlist", methods=["POST"])
def waitlist():
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Request body must be JSON."}), 400

    email = body.get("email", "").strip()
    business_name = body.get("business_name", "").strip()
    score = body.get("score")

    if not email:
        return jsonify({"error": "Field 'email' is required."}), 400
    if "@" not in email:
        return jsonify({"error": "Field 'email' must be a valid email address."}), 400
    if score is None:
        return jsonify({"error": "Field 'score' is required."}), 400

    try:
        score = float(score)
    except (TypeError, ValueError):
        return jsonify({"error": "Field 'score' must be numeric."}), 400

    try:
        save_waitlist_entry(email, business_name, score)
    except Exception as exc:
        app.logger.exception("save_waitlist_entry failed")
        return jsonify({"error": f"Could not save waitlist entry: {exc}"}), 500

    return jsonify({"ok": True, "message": "You're on the list."})


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

"""
Seed benchmarks.db with 20 realistic agency profiles.
Run once: python seed_benchmarks.py
"""
from pipeline import calculate_ratios, calculate_composite_score, save_benchmark

profiles = [
    # --- Small, healthy ---
    {"revenue_current": 42000, "revenue_1m_ago": 39000, "revenue_3m_ago": 36000,
     "expenses_current": 22000, "expenses_3m_ago": 21000, "cash_balance": 85000,
     "top_client_revenue": 8000,  "accounts_receivable": 32000, "num_employees": 5,
     "gross_margin_current": 0.53, "gross_margin_3m_ago": 0.51},

    {"revenue_current": 68000, "revenue_1m_ago": 65000, "revenue_3m_ago": 61000,
     "expenses_current": 36000, "expenses_3m_ago": 34000, "cash_balance": 130000,
     "top_client_revenue": 12000, "accounts_receivable": 38000, "num_employees": 8,
     "gross_margin_current": 0.56, "gross_margin_3m_ago": 0.54},

    {"revenue_current": 55000, "revenue_1m_ago": 53000, "revenue_3m_ago": 50000,
     "expenses_current": 29000, "expenses_3m_ago": 28000, "cash_balance": 110000,
     "top_client_revenue": 10000, "accounts_receivable": 28000, "num_employees": 7,
     "gross_margin_current": 0.59, "gross_margin_3m_ago": 0.57},

    # --- Small, struggling ---
    {"revenue_current": 30000, "revenue_1m_ago": 31000, "revenue_3m_ago": 32000,
     "expenses_current": 24000, "expenses_3m_ago": 22000, "cash_balance": 18000,
     "top_client_revenue": 18000, "accounts_receivable": 48000, "num_employees": 4,
     "gross_margin_current": 0.46, "gross_margin_3m_ago": 0.50},

    {"revenue_current": 38000, "revenue_1m_ago": 38500, "revenue_3m_ago": 39000,
     "expenses_current": 30000, "expenses_3m_ago": 27000, "cash_balance": 22000,
     "top_client_revenue": 14000, "accounts_receivable": 62000, "num_employees": 6,
     "gross_margin_current": 0.44, "gross_margin_3m_ago": 0.47},

    # --- Small, critical ---
    {"revenue_current": 18000, "revenue_1m_ago": 20000, "revenue_3m_ago": 23000,
     "expenses_current": 19500, "expenses_3m_ago": 18000, "cash_balance": 8000,
     "top_client_revenue": 12000, "accounts_receivable": 75000, "num_employees": 3,
     "gross_margin_current": 0.36, "gross_margin_3m_ago": 0.42},

    {"revenue_current": 22000, "revenue_1m_ago": 24000, "revenue_3m_ago": 27000,
     "expenses_current": 24500, "expenses_3m_ago": 22000, "cash_balance": 5000,
     "top_client_revenue": 15000, "accounts_receivable": 90000, "num_employees": 5,
     "gross_margin_current": 0.33, "gross_margin_3m_ago": 0.40},

    # --- Medium, healthy ---
    {"revenue_current": 140000, "revenue_1m_ago": 133000, "revenue_3m_ago": 125000,
     "expenses_current": 74000,  "expenses_3m_ago": 71000,  "cash_balance": 280000,
     "top_client_revenue": 25000, "accounts_receivable": 60000, "num_employees": 15,
     "gross_margin_current": 0.55, "gross_margin_3m_ago": 0.53},

    {"revenue_current": 210000, "revenue_1m_ago": 200000, "revenue_3m_ago": 190000,
     "expenses_current": 110000, "expenses_3m_ago": 106000, "cash_balance": 420000,
     "top_client_revenue": 38000, "accounts_receivable": 85000, "num_employees": 22,
     "gross_margin_current": 0.58, "gross_margin_3m_ago": 0.56},

    {"revenue_current": 165000, "revenue_1m_ago": 158000, "revenue_3m_ago": 150000,
     "expenses_current": 87000,  "expenses_3m_ago": 84000,  "cash_balance": 330000,
     "top_client_revenue": 30000, "accounts_receivable": 70000, "num_employees": 18,
     "gross_margin_current": 0.54, "gross_margin_3m_ago": 0.52},

    # --- Medium, struggling ---
    {"revenue_current": 88000,  "revenue_1m_ago": 90000,  "revenue_3m_ago": 92000,
     "expenses_current": 72000,  "expenses_3m_ago": 65000,  "cash_balance": 45000,
     "top_client_revenue": 40000, "accounts_receivable": 110000, "num_employees": 12,
     "gross_margin_current": 0.47, "gross_margin_3m_ago": 0.51},

    {"revenue_current": 185000, "revenue_1m_ago": 187000, "revenue_3m_ago": 190000,
     "expenses_current": 165000, "expenses_3m_ago": 148000, "cash_balance": 60000,
     "top_client_revenue": 45000, "accounts_receivable": 140000, "num_employees": 25,
     "gross_margin_current": 0.42, "gross_margin_3m_ago": 0.46},

    {"revenue_current": 102000, "revenue_1m_ago": 104000, "revenue_3m_ago": 106000,
     "expenses_current": 83000,  "expenses_3m_ago": 75000,  "cash_balance": 35000,
     "top_client_revenue": 35000, "accounts_receivable": 120000, "num_employees": 14,
     "gross_margin_current": 0.44, "gross_margin_3m_ago": 0.48},

    # --- Medium, critical ---
    {"revenue_current": 115000, "revenue_1m_ago": 122000, "revenue_3m_ago": 130000,
     "expenses_current": 126000, "expenses_3m_ago": 112000, "cash_balance": 20000,
     "top_client_revenue": 55000, "accounts_receivable": 175000, "num_employees": 20,
     "gross_margin_current": 0.37, "gross_margin_3m_ago": 0.44},

    # --- Large, healthy ---
    {"revenue_current": 520000, "revenue_1m_ago": 495000, "revenue_3m_ago": 470000,
     "expenses_current": 268000, "expenses_3m_ago": 258000, "cash_balance": 950000,
     "top_client_revenue": 75000, "accounts_receivable": 180000, "num_employees": 45,
     "gross_margin_current": 0.57, "gross_margin_3m_ago": 0.55},

    {"revenue_current": 720000, "revenue_1m_ago": 690000, "revenue_3m_ago": 660000,
     "expenses_current": 375000, "expenses_3m_ago": 362000, "cash_balance": 1400000,
     "top_client_revenue": 90000, "accounts_receivable": 240000, "num_employees": 60,
     "gross_margin_current": 0.60, "gross_margin_3m_ago": 0.58},

    # --- Large, struggling ---
    {"revenue_current": 320000, "revenue_1m_ago": 328000, "revenue_3m_ago": 335000,
     "expenses_current": 292000, "expenses_3m_ago": 265000, "cash_balance": 80000,
     "top_client_revenue": 120000, "accounts_receivable": 350000, "num_employees": 38,
     "gross_margin_current": 0.44, "gross_margin_3m_ago": 0.49},

    {"revenue_current": 410000, "revenue_1m_ago": 415000, "revenue_3m_ago": 420000,
     "expenses_current": 380000, "expenses_3m_ago": 345000, "cash_balance": 55000,
     "top_client_revenue": 140000, "accounts_receivable": 420000, "num_employees": 48,
     "gross_margin_current": 0.40, "gross_margin_3m_ago": 0.45},

    # --- Large, critical ---
    {"revenue_current": 380000, "revenue_1m_ago": 400000, "revenue_3m_ago": 425000,
     "expenses_current": 425000, "expenses_3m_ago": 385000, "cash_balance": 30000,
     "top_client_revenue": 150000, "accounts_receivable": 520000, "num_employees": 50,
     "gross_margin_current": 0.35, "gross_margin_3m_ago": 0.43},

    {"revenue_current": 295000, "revenue_1m_ago": 315000, "revenue_3m_ago": 340000,
     "expenses_current": 340000, "expenses_3m_ago": 305000, "cash_balance": 15000,
     "top_client_revenue": 130000, "accounts_receivable": 480000, "num_employees": 42,
     "gross_margin_current": 0.32, "gross_margin_3m_ago": 0.40},
]

if __name__ == "__main__":
    inserted = 0
    for i, data in enumerate(profiles, 1):
        try:
            ratios = calculate_ratios(data)
            composite_score, _ = calculate_composite_score(ratios)
            save_benchmark(data, ratios, composite_score)
            n = data["num_employees"]
            size = "small" if n <= 10 else ("medium" if n <= 30 else "large")
            print(f"  [{i:02d}] {size:6s}  score={composite_score:5.1f}")
            inserted += 1
        except Exception as e:
            print(f"  [{i:02d}] ERROR: {e}")

    print(f"\nDone — {inserted}/{len(profiles)} profiles inserted into benchmarks.db")

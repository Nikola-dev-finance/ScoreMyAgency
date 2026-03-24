"""
Seed benchmarks.db with 56 realistic agency profiles.
Wipes existing seed data and re-inserts on every run.

Profiles are spread across:
  - All three size buckets (small / medium / large)
  - Full range of each individual ratio (not just composite score)
  - Healthy / struggling / critical composites

Run once: python seed_benchmarks.py
"""
import sqlite3
from pipeline import DB_PATH, _init_db, calculate_ratios, calculate_composite_score, save_benchmark

# ---------------------------------------------------------------------------
# 50 hand-crafted profiles — each row is a data dict matching parse_csv() format.
# Key design rule: vary EACH ratio independently so the percentile pool has
# spread along every dimension, not just composite score.
# ---------------------------------------------------------------------------
# Legend for comments:
#   rev_conc = revenue_concentration (top_client / revenue_current)
#   dso      = (AR / revenue_current) * 30
#   runway   = cash_balance / expenses_current
#   gm       = gross_margin_current
#   evr      = expense_vs_revenue_growth (exp growth - rev growth)
#   rpe      = revenue_per_employee (annualised)

profiles = [
    # =========================================================
    # SMALL  (1-10 employees)  — 20 profiles
    # =========================================================

    # --- very healthy across all ratios ---
    {"revenue_current": 50000,  "revenue_1m_ago": 47000,  "revenue_3m_ago": 44000,
     "expenses_current": 24000, "expenses_3m_ago": 23000, "cash_balance": 180000,
     "top_client_revenue": 7000,  "accounts_receivable": 20000, "num_employees": 5,
     "gross_margin_current": 0.66, "gross_margin_3m_ago": 0.64},   # gm high, conc 14%, dso 12, runway 7.5

    {"revenue_current": 72000,  "revenue_1m_ago": 68000,  "revenue_3m_ago": 64000,
     "expenses_current": 33000, "expenses_3m_ago": 32000, "cash_balance": 250000,
     "top_client_revenue": 10000, "accounts_receivable": 22000, "num_employees": 8,
     "gross_margin_current": 0.60, "gross_margin_3m_ago": 0.58},   # runway 7.6, conc 14%, dso 9

    {"revenue_current": 45000,  "revenue_1m_ago": 43000,  "revenue_3m_ago": 41000,
     "expenses_current": 21000, "expenses_3m_ago": 20500, "cash_balance": 155000,
     "top_client_revenue": 9000,  "accounts_receivable": 18000, "num_employees": 5,
     "gross_margin_current": 0.62, "gross_margin_3m_ago": 0.61},   # runway 7.4, conc 20%, dso 12

    # --- good composite, but weak on one ratio each ---
    {"revenue_current": 60000,  "revenue_1m_ago": 58000,  "revenue_3m_ago": 56000,
     "expenses_current": 32000, "expenses_3m_ago": 30500, "cash_balance": 96000,
     "top_client_revenue": 22000, "accounts_receivable": 24000, "num_employees": 7,
     "gross_margin_current": 0.57, "gross_margin_3m_ago": 0.56},   # conc 37% (weak)

    {"revenue_current": 55000,  "revenue_1m_ago": 53000,  "revenue_3m_ago": 51000,
     "expenses_current": 28000, "expenses_3m_ago": 27000, "cash_balance": 84000,
     "top_client_revenue": 12000, "accounts_receivable": 55000, "num_employees": 6,
     "gross_margin_current": 0.58, "gross_margin_3m_ago": 0.57},   # dso 30 days (borderline)

    {"revenue_current": 48000,  "revenue_1m_ago": 46000,  "revenue_3m_ago": 44000,
     "expenses_current": 26000, "expenses_3m_ago": 24000, "cash_balance": 78000,
     "top_client_revenue": 10000, "accounts_receivable": 20000, "num_employees": 5,
     "gross_margin_current": 0.47, "gross_margin_3m_ago": 0.50},   # gm declining (was 50%, now 47%)

    {"revenue_current": 52000,  "revenue_1m_ago": 51000,  "revenue_3m_ago": 50000,
     "expenses_current": 27000, "expenses_3m_ago": 24000, "cash_balance": 81000,
     "top_client_revenue": 11000, "accounts_receivable": 21000, "num_employees": 6,
     "gross_margin_current": 0.56, "gross_margin_3m_ago": 0.55},   # expenses growing faster than flat revenue

    # --- mid-range / struggling ---
    {"revenue_current": 35000,  "revenue_1m_ago": 36000,  "revenue_3m_ago": 37000,
     "expenses_current": 27000, "expenses_3m_ago": 24000, "cash_balance": 40000,
     "top_client_revenue": 14000, "accounts_receivable": 42000, "num_employees": 5,
     "gross_margin_current": 0.46, "gross_margin_3m_ago": 0.49},   # declining revenue, expenses up

    {"revenue_current": 42000,  "revenue_1m_ago": 41500,  "revenue_3m_ago": 41000,
     "expenses_current": 33000, "expenses_3m_ago": 29000, "cash_balance": 42000,
     "top_client_revenue": 18000, "accounts_receivable": 63000, "num_employees": 6,
     "gross_margin_current": 0.44, "gross_margin_3m_ago": 0.47},   # dso 45 days (dangerous), conc 43%

    {"revenue_current": 28000,  "revenue_1m_ago": 29000,  "revenue_3m_ago": 30000,
     "expenses_current": 22000, "expenses_3m_ago": 20000, "cash_balance": 33000,
     "top_client_revenue": 16000, "accounts_receivable": 50000, "num_employees": 4,
     "gross_margin_current": 0.43, "gross_margin_3m_ago": 0.48},   # revenue shrinking 7%

    {"revenue_current": 38000,  "revenue_1m_ago": 38000,  "revenue_3m_ago": 38000,
     "expenses_current": 29000, "expenses_3m_ago": 26000, "cash_balance": 35000,
     "top_client_revenue": 20000, "accounts_receivable": 76000, "num_employees": 5,
     "gross_margin_current": 0.42, "gross_margin_3m_ago": 0.45},   # dso 60 days

    {"revenue_current": 32000,  "revenue_1m_ago": 33000,  "revenue_3m_ago": 34000,
     "expenses_current": 25000, "expenses_3m_ago": 22000, "cash_balance": 25000,
     "top_client_revenue": 19000, "accounts_receivable": 80000, "num_employees": 4,
     "gross_margin_current": 0.39, "gross_margin_3m_ago": 0.43},   # dso 75 days, conc 59%

    # --- critical ---
    {"revenue_current": 20000,  "revenue_1m_ago": 22000,  "revenue_3m_ago": 25000,
     "expenses_current": 21500, "expenses_3m_ago": 19000, "cash_balance": 9000,
     "top_client_revenue": 14000, "accounts_receivable": 90000, "num_employees": 3,
     "gross_margin_current": 0.35, "gross_margin_3m_ago": 0.42},   # runway 0.4, dso 135

    {"revenue_current": 25000,  "revenue_1m_ago": 27000,  "revenue_3m_ago": 30000,
     "expenses_current": 26000, "expenses_3m_ago": 23000, "cash_balance": 7500,
     "top_client_revenue": 18000, "accounts_receivable": 110000, "num_employees": 4,
     "gross_margin_current": 0.32, "gross_margin_3m_ago": 0.39},   # burning cash, dso 132

    {"revenue_current": 18000,  "revenue_1m_ago": 20000,  "revenue_3m_ago": 23000,
     "expenses_current": 22000, "expenses_3m_ago": 19500, "cash_balance": 4000,
     "top_client_revenue": 15000, "accounts_receivable": 130000, "num_employees": 3,
     "gross_margin_current": 0.28, "gross_margin_3m_ago": 0.36},   # all ratios red

    {"revenue_current": 15000,  "revenue_1m_ago": 17000,  "revenue_3m_ago": 20000,
     "expenses_current": 18000, "expenses_3m_ago": 16000, "cash_balance": 3000,
     "top_client_revenue": 12000, "accounts_receivable": 150000, "num_employees": 2,
     "gross_margin_current": 0.25, "gross_margin_3m_ago": 0.33},   # runway 0.17, dso 300

    {"revenue_current": 30000,  "revenue_1m_ago": 32000,  "revenue_3m_ago": 35000,
     "expenses_current": 32000, "expenses_3m_ago": 28000, "cash_balance": 6000,
     "top_client_revenue": 25000, "accounts_receivable": 95000, "num_employees": 5,
     "gross_margin_current": 0.30, "gross_margin_3m_ago": 0.38},   # revenue down 14%, conc 83%

    {"revenue_current": 22000,  "revenue_1m_ago": 24000,  "revenue_3m_ago": 27000,
     "expenses_current": 25000, "expenses_3m_ago": 22000, "cash_balance": 5000,
     "top_client_revenue": 17000, "accounts_receivable": 100000, "num_employees": 3,
     "gross_margin_current": 0.27, "gross_margin_3m_ago": 0.35},

    {"revenue_current": 27000,  "revenue_1m_ago": 29000,  "revenue_3m_ago": 32000,
     "expenses_current": 29500, "expenses_3m_ago": 26000, "cash_balance": 5500,
     "top_client_revenue": 22000, "accounts_receivable": 120000, "num_employees": 4,
     "gross_margin_current": 0.29, "gross_margin_3m_ago": 0.37},

    {"revenue_current": 12000,  "revenue_1m_ago": 14000,  "revenue_3m_ago": 17000,
     "expenses_current": 15000, "expenses_3m_ago": 13500, "cash_balance": 2000,
     "top_client_revenue": 10000, "accounts_receivable": 120000, "num_employees": 2,
     "gross_margin_current": 0.22, "gross_margin_3m_ago": 0.30},   # worst small profile

    # =========================================================
    # MEDIUM  (11-30 employees)  — 20 profiles
    # =========================================================

    # --- very healthy ---
    {"revenue_current": 170000, "revenue_1m_ago": 162000, "revenue_3m_ago": 154000,
     "expenses_current": 85000,  "expenses_3m_ago": 82000,  "cash_balance": 600000,
     "top_client_revenue": 28000, "accounts_receivable": 55000, "num_employees": 15,
     "gross_margin_current": 0.63, "gross_margin_3m_ago": 0.61},   # runway 7.1, conc 16%

    {"revenue_current": 240000, "revenue_1m_ago": 228000, "revenue_3m_ago": 216000,
     "expenses_current": 118000, "expenses_3m_ago": 114000, "cash_balance": 850000,
     "top_client_revenue": 38000, "accounts_receivable": 72000, "num_employees": 22,
     "gross_margin_current": 0.61, "gross_margin_3m_ago": 0.59},   # runway 7.2, dso 9

    {"revenue_current": 195000, "revenue_1m_ago": 185000, "revenue_3m_ago": 175000,
     "expenses_current": 98000,  "expenses_3m_ago": 95000,  "cash_balance": 720000,
     "top_client_revenue": 32000, "accounts_receivable": 60000, "num_employees": 18,
     "gross_margin_current": 0.60, "gross_margin_3m_ago": 0.58},

    {"revenue_current": 155000, "revenue_1m_ago": 148000, "revenue_3m_ago": 141000,
     "expenses_current": 78000,  "expenses_3m_ago": 75000,  "cash_balance": 550000,
     "top_client_revenue": 25000, "accounts_receivable": 50000, "num_employees": 14,
     "gross_margin_current": 0.65, "gross_margin_3m_ago": 0.63},

    # --- good but weak on individual ratios ---
    {"revenue_current": 180000, "revenue_1m_ago": 175000, "revenue_3m_ago": 170000,
     "expenses_current": 95000,  "expenses_3m_ago": 88000,  "cash_balance": 285000,
     "top_client_revenue": 72000, "accounts_receivable": 65000, "num_employees": 17,
     "gross_margin_current": 0.55, "gross_margin_3m_ago": 0.54},   # conc 40% (risky)

    {"revenue_current": 145000, "revenue_1m_ago": 143000, "revenue_3m_ago": 141000,
     "expenses_current": 76000,  "expenses_3m_ago": 70000,  "cash_balance": 230000,
     "top_client_revenue": 30000, "accounts_receivable": 120000, "num_employees": 13,
     "gross_margin_current": 0.54, "gross_margin_3m_ago": 0.53},   # dso 25 → expenses growing

    {"revenue_current": 165000, "revenue_1m_ago": 162000, "revenue_3m_ago": 160000,
     "expenses_current": 88000,  "expenses_3m_ago": 80000,  "cash_balance": 265000,
     "top_client_revenue": 35000, "accounts_receivable": 70000, "num_employees": 15,
     "gross_margin_current": 0.50, "gross_margin_3m_ago": 0.53},   # gm declining

    # --- struggling ---
    {"revenue_current": 110000, "revenue_1m_ago": 113000, "revenue_3m_ago": 116000,
     "expenses_current": 90000,  "expenses_3m_ago": 80000,  "cash_balance": 55000,
     "top_client_revenue": 50000, "accounts_receivable": 140000, "num_employees": 12,
     "gross_margin_current": 0.46, "gross_margin_3m_ago": 0.50},   # conc 45%, dso 38, runway 0.6

    {"revenue_current": 200000, "revenue_1m_ago": 202000, "revenue_3m_ago": 205000,
     "expenses_current": 178000, "expenses_3m_ago": 160000, "cash_balance": 70000,
     "top_client_revenue": 55000, "accounts_receivable": 160000, "num_employees": 25,
     "gross_margin_current": 0.43, "gross_margin_3m_ago": 0.47},   # expenses exploding

    {"revenue_current": 125000, "revenue_1m_ago": 128000, "revenue_3m_ago": 131000,
     "expenses_current": 102000, "expenses_3m_ago": 91000,  "cash_balance": 40000,
     "top_client_revenue": 45000, "accounts_receivable": 175000, "num_employees": 14,
     "gross_margin_current": 0.44, "gross_margin_3m_ago": 0.48},   # dso 42, conc 36%

    {"revenue_current": 95000,  "revenue_1m_ago": 98000,  "revenue_3m_ago": 102000,
     "expenses_current": 78000,  "expenses_3m_ago": 70000,  "cash_balance": 48000,
     "top_client_revenue": 38000, "accounts_receivable": 130000, "num_employees": 11,
     "gross_margin_current": 0.42, "gross_margin_3m_ago": 0.46},

    {"revenue_current": 140000, "revenue_1m_ago": 143000, "revenue_3m_ago": 147000,
     "expenses_current": 118000, "expenses_3m_ago": 105000, "cash_balance": 35000,
     "top_client_revenue": 60000, "accounts_receivable": 200000, "num_employees": 16,
     "gross_margin_current": 0.40, "gross_margin_3m_ago": 0.45},   # conc 43%, dso 43, runway 0.3

    {"revenue_current": 115000, "revenue_1m_ago": 118000, "revenue_3m_ago": 121000,
     "expenses_current": 95000,  "expenses_3m_ago": 84000,  "cash_balance": 28000,
     "top_client_revenue": 52000, "accounts_receivable": 190000, "num_employees": 13,
     "gross_margin_current": 0.41, "gross_margin_3m_ago": 0.46},

    # --- critical ---
    {"revenue_current": 130000, "revenue_1m_ago": 138000, "revenue_3m_ago": 147000,
     "expenses_current": 143000, "expenses_3m_ago": 128000, "cash_balance": 22000,
     "top_client_revenue": 65000, "accounts_receivable": 260000, "num_employees": 20,
     "gross_margin_current": 0.36, "gross_margin_3m_ago": 0.44},

    {"revenue_current": 105000, "revenue_1m_ago": 112000, "revenue_3m_ago": 120000,
     "expenses_current": 120000, "expenses_3m_ago": 107000, "cash_balance": 12000,
     "top_client_revenue": 60000, "accounts_receivable": 290000, "num_employees": 15,
     "gross_margin_current": 0.33, "gross_margin_3m_ago": 0.41},   # revenue -12.5%, all red

    {"revenue_current": 88000,  "revenue_1m_ago": 95000,  "revenue_3m_ago": 103000,
     "expenses_current": 100000, "expenses_3m_ago": 90000,  "cash_balance": 8000,
     "top_client_revenue": 55000, "accounts_receivable": 310000, "num_employees": 13,
     "gross_margin_current": 0.30, "gross_margin_3m_ago": 0.39},

    {"revenue_current": 75000,  "revenue_1m_ago": 82000,  "revenue_3m_ago": 91000,
     "expenses_current": 88000,  "expenses_3m_ago": 78000,  "cash_balance": 5000,
     "top_client_revenue": 50000, "accounts_receivable": 350000, "num_employees": 12,
     "gross_margin_current": 0.26, "gross_margin_3m_ago": 0.35},   # worst medium

    {"revenue_current": 120000, "revenue_1m_ago": 128000, "revenue_3m_ago": 138000,
     "expenses_current": 135000, "expenses_3m_ago": 120000, "cash_balance": 15000,
     "top_client_revenue": 70000, "accounts_receivable": 280000, "num_employees": 18,
     "gross_margin_current": 0.34, "gross_margin_3m_ago": 0.43},

    {"revenue_current": 160000, "revenue_1m_ago": 170000, "revenue_3m_ago": 182000,
     "expenses_current": 175000, "expenses_3m_ago": 155000, "cash_balance": 18000,
     "top_client_revenue": 80000, "accounts_receivable": 320000, "num_employees": 24,
     "gross_margin_current": 0.35, "gross_margin_3m_ago": 0.44},

    {"revenue_current": 98000,  "revenue_1m_ago": 105000, "revenue_3m_ago": 113000,
     "expenses_current": 110000, "expenses_3m_ago": 98000,  "cash_balance": 10000,
     "top_client_revenue": 58000, "accounts_receivable": 300000, "num_employees": 16,
     "gross_margin_current": 0.31, "gross_margin_3m_ago": 0.40},

    # =========================================================
    # LARGE  (31+ employees)  — 10 profiles
    # =========================================================

    # --- healthy ---
    {"revenue_current": 550000, "revenue_1m_ago": 523000, "revenue_3m_ago": 496000,
     "expenses_current": 280000, "expenses_3m_ago": 270000, "cash_balance": 1800000,
     "top_client_revenue": 80000,  "accounts_receivable": 165000, "num_employees": 48,
     "gross_margin_current": 0.60, "gross_margin_3m_ago": 0.58},

    {"revenue_current": 780000, "revenue_1m_ago": 742000, "revenue_3m_ago": 705000,
     "expenses_current": 395000, "expenses_3m_ago": 383000, "cash_balance": 2500000,
     "top_client_revenue": 100000, "accounts_receivable": 220000, "num_employees": 65,
     "gross_margin_current": 0.62, "gross_margin_3m_ago": 0.60},

    {"revenue_current": 420000, "revenue_1m_ago": 400000, "revenue_3m_ago": 380000,
     "expenses_current": 212000, "expenses_3m_ago": 205000, "cash_balance": 1350000,
     "top_client_revenue": 65000,  "accounts_receivable": 130000, "num_employees": 36,
     "gross_margin_current": 0.58, "gross_margin_3m_ago": 0.56},

    {"revenue_current": 650000, "revenue_1m_ago": 620000, "revenue_3m_ago": 590000,
     "expenses_current": 330000, "expenses_3m_ago": 319000, "cash_balance": 2100000,
     "top_client_revenue": 90000,  "accounts_receivable": 185000, "num_employees": 55,
     "gross_margin_current": 0.59, "gross_margin_3m_ago": 0.57},

    # --- struggling ---
    {"revenue_current": 380000, "revenue_1m_ago": 385000, "revenue_3m_ago": 390000,
     "expenses_current": 345000, "expenses_3m_ago": 310000, "cash_balance": 90000,
     "top_client_revenue": 145000, "accounts_receivable": 420000, "num_employees": 40,
     "gross_margin_current": 0.44, "gross_margin_3m_ago": 0.49},

    {"revenue_current": 520000, "revenue_1m_ago": 527000, "revenue_3m_ago": 534000,
     "expenses_current": 475000, "expenses_3m_ago": 427000, "cash_balance": 65000,
     "top_client_revenue": 180000, "accounts_receivable": 560000, "num_employees": 55,
     "gross_margin_current": 0.42, "gross_margin_3m_ago": 0.46},

    {"revenue_current": 440000, "revenue_1m_ago": 448000, "revenue_3m_ago": 456000,
     "expenses_current": 400000, "expenses_3m_ago": 358000, "cash_balance": 75000,
     "top_client_revenue": 160000, "accounts_receivable": 490000, "num_employees": 48,
     "gross_margin_current": 0.41, "gross_margin_3m_ago": 0.46},

    # --- critical ---
    {"revenue_current": 410000, "revenue_1m_ago": 438000, "revenue_3m_ago": 470000,
     "expenses_current": 460000, "expenses_3m_ago": 415000, "cash_balance": 32000,
     "top_client_revenue": 165000, "accounts_receivable": 580000, "num_employees": 50,
     "gross_margin_current": 0.36, "gross_margin_3m_ago": 0.44},

    {"revenue_current": 330000, "revenue_1m_ago": 355000, "revenue_3m_ago": 382000,
     "expenses_current": 375000, "expenses_3m_ago": 338000, "cash_balance": 18000,
     "top_client_revenue": 150000, "accounts_receivable": 650000, "num_employees": 42,
     "gross_margin_current": 0.33, "gross_margin_3m_ago": 0.42},

    {"revenue_current": 290000, "revenue_1m_ago": 315000, "revenue_3m_ago": 345000,
     "expenses_current": 340000, "expenses_3m_ago": 305000, "cash_balance": 10000,
     "top_client_revenue": 140000, "accounts_receivable": 700000, "num_employees": 38,
     "gross_margin_current": 0.28, "gross_margin_3m_ago": 0.38},

    # =========================================================
    # SMALL — extra profiles covering low revenue-per-employee range
    # (7-10 employees with modest revenue → rpe €40k-€65k)
    # Without these, agencies like BrightSpark (€57k rpe, 8 employees)
    # score 0th percentile because the pool only had 2-5 employee criticals.
    # =========================================================

    {"revenue_current": 34000,  "revenue_1m_ago": 35000,  "revenue_3m_ago": 36000,
     "expenses_current": 32000, "expenses_3m_ago": 29000, "cash_balance": 12000,
     "top_client_revenue": 18000, "accounts_receivable": 85000, "num_employees": 9,
     "gross_margin_current": 0.38, "gross_margin_3m_ago": 0.42},   # rpe ≈ 45.3k

    {"revenue_current": 38000,  "revenue_1m_ago": 40000,  "revenue_3m_ago": 42000,
     "expenses_current": 36000, "expenses_3m_ago": 32000, "cash_balance": 9000,
     "top_client_revenue": 20000, "accounts_receivable": 95000, "num_employees": 10,
     "gross_margin_current": 0.36, "gross_margin_3m_ago": 0.41},   # rpe ≈ 48.0k

    {"revenue_current": 42000,  "revenue_1m_ago": 43000,  "revenue_3m_ago": 44000,
     "expenses_current": 38000, "expenses_3m_ago": 34000, "cash_balance": 10000,
     "top_client_revenue": 22000, "accounts_receivable": 100000, "num_employees": 9,
     "gross_margin_current": 0.37, "gross_margin_3m_ago": 0.42},   # rpe ≈ 55.6k

    {"revenue_current": 45000,  "revenue_1m_ago": 46000,  "revenue_3m_ago": 47000,
     "expenses_current": 42000, "expenses_3m_ago": 38000, "cash_balance": 8000,
     "top_client_revenue": 24000, "accounts_receivable": 115000, "num_employees": 10,
     "gross_margin_current": 0.35, "gross_margin_3m_ago": 0.40},   # rpe ≈ 55.2k

    {"revenue_current": 36000,  "revenue_1m_ago": 37500,  "revenue_3m_ago": 39000,
     "expenses_current": 33000, "expenses_3m_ago": 30000, "cash_balance": 14000,
     "top_client_revenue": 19000, "accounts_receivable": 80000, "num_employees": 8,
     "gross_margin_current": 0.39, "gross_margin_3m_ago": 0.43},   # rpe ≈ 53.0k

    {"revenue_current": 48000,  "revenue_1m_ago": 49500,  "revenue_3m_ago": 51000,
     "expenses_current": 44000, "expenses_3m_ago": 40000, "cash_balance": 11000,
     "top_client_revenue": 25000, "accounts_receivable": 120000, "num_employees": 10,
     "gross_margin_current": 0.34, "gross_margin_3m_ago": 0.39},   # rpe ≈ 59.4k
]


if __name__ == "__main__":
    assert len(profiles) == 56, f"Expected 56 profiles, got {len(profiles)}"

    _init_db()

    # Wipe existing rows so re-running produces a clean, predictable pool
    with sqlite3.connect(DB_PATH) as conn:
        deleted = conn.execute("DELETE FROM agency_benchmarks").rowcount
        conn.commit()
    print(f"Cleared {deleted} existing rows\n")

    inserted = 0
    size_counts = {"small": 0, "medium": 0, "large": 0}
    score_buckets = {"healthy (70+)": 0, "struggling (40-69)": 0, "critical (<40)": 0}

    for i, data in enumerate(profiles, 1):
        try:
            ratios = calculate_ratios(data)
            composite_score, _ = calculate_composite_score(ratios)
            save_benchmark(data, ratios, composite_score)
            n = data["num_employees"]
            size = "small" if n <= 10 else ("medium" if n <= 30 else "large")
            size_counts[size] += 1
            bucket = ("healthy (70+)" if composite_score >= 70
                      else "struggling (40-69)" if composite_score >= 40
                      else "critical (<40)")
            score_buckets[bucket] += 1
            print(f"  [{i:02d}] {size:6s}  score={composite_score:5.1f}  "
                  f"rev_conc={ratios['revenue_concentration']:.2f}  "
                  f"dso={ratios['dso']:5.1f}  runway={ratios['cash_runway']:.2f}  "
                  f"gm={ratios['gross_margin_current']:.2f}")
            inserted += 1
        except Exception as e:
            print(f"  [{i:02d}] ERROR: {e}")

    print(f"\nDone — {inserted}/50 profiles inserted")
    print(f"By size:  {size_counts}")
    print(f"By score: {score_buckets}")

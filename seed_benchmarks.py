"""
Re-seed benchmarks.db from the canonical profile list in pipeline.py.
Wipes existing rows and re-inserts all profiles on every run.

Run once (or to reset): python seed_benchmarks.py
"""
import sqlite3

if __name__ == "__main__":
    from pipeline import (
        _SEED_PROFILES, _init_db, DB_PATH,
        calculate_ratios, calculate_composite_score, save_benchmark,
    )

    _init_db()

    with sqlite3.connect(DB_PATH) as conn:
        deleted = conn.execute("DELETE FROM agency_benchmarks").rowcount
        conn.commit()
    print(f"Cleared {deleted} existing rows\n")

    inserted = 0
    size_counts   = {"small": 0, "medium": 0, "large": 0}
    score_buckets = {"healthy (70+)": 0, "struggling (40-69)": 0, "critical (<40)": 0}

    for i, data in enumerate(_SEED_PROFILES, 1):
        try:
            ratios = calculate_ratios(data)
            composite_score, _ = calculate_composite_score(ratios)
            save_benchmark(data, ratios, composite_score)
            n    = data["num_employees"]
            size = "small" if n <= 10 else ("medium" if n <= 30 else "large")
            size_counts[size] += 1
            bucket = ("healthy (70+)"      if composite_score >= 70 else
                      "struggling (40-69)" if composite_score >= 40 else
                      "critical (<40)")
            score_buckets[bucket] += 1
            print(f"  [{i:02d}] {size:6s}  score={composite_score:5.1f}  "
                  f"rev_conc={ratios['revenue_concentration']:.2f}  "
                  f"dso={ratios['dso']:5.1f}  runway={ratios['cash_runway']:.2f}  "
                  f"gm={ratios['gross_margin_current']:.2f}")
            inserted += 1
        except Exception as e:
            print(f"  [{i:02d}] ERROR: {e}")

    print(f"\nDone — {inserted}/{len(_SEED_PROFILES)} profiles inserted")
    print(f"By size:  {size_counts}")
    print(f"By score: {score_buckets}")

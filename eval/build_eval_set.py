"""
Build the 50-question evaluation set for the question-to-SQL layer.

Every question's expected answer is computed directly from fct_lgps_fund_year
with plain SQL (the ground truth), independent of the AI layer being tested.
Questions are generated from templates sampled across funds and years so the
set spans costs, contributions, membership and asset growth.
"""

import json
import random
from pathlib import Path

import duckdb

random.seed(42)

DB_PATH = "dev.duckdb"
OUT_PATH = Path("eval/questions.json")

# Each template needs a (fund, year) pair where `column` is non-null, and
# renders a question whose answer is that column's value for that fund/year.
SCALAR_TEMPLATES = [
    ("total_expenditure", "What was {fund}'s total expenditure in {year}?"),
    ("pension_benefits_paid", "How much did {fund} pay out in pension benefits in {year}?"),
    ("contributions_employees", "What were {fund}'s total employee contributions in {year}?"),
    ("contributions_employers", "What were {fund}'s total employer contributions in {year}?"),
    ("investment_income", "What was {fund}'s investment income in {year}?"),
    ("total_income", "What was {fund}'s total income in {year}?"),
    ("total_contributing_members", "How many contributing members did {fund} have in {year}?"),
    ("total_pensioners", "How many pensioners did {fund} have in {year}?"),
    ("total_employers", "How many employers participated in {fund} in {year}?"),
    ("total_members", "What was the total membership of {fund} in {year}?"),
    ("market_value_end_of_year", "What was the market value of {fund}'s fund at the end of {year}?"),
    ("admin_and_mgmt_costs", "What were {fund}'s administration and management costs in {year}?"),
]

GROWTH_TEMPLATE = "By how much did the market value of {fund}'s fund grow during {year} (end of year value minus start of year value)?"

RANKING_TEMPLATE = "Which fund had the highest total income in {year}?"

N_PER_SCALAR_TEMPLATE = 3
N_GROWTH = 8
N_RANKING = 6


def main():
    con = duckdb.connect(DB_PATH, read_only=True)
    funds = con.sql(
        "select distinct ecode, local_authority from fct_lgps_fund_year where fund_type = 'fund'"
    ).df()
    years = [r[0] for r in con.sql("select distinct year from fct_lgps_fund_year order by 1").fetchall()]

    questions = []
    qid = 1

    for column, template in SCALAR_TEMPLATES:
        candidates = con.sql(f"""
            select ecode, local_authority, year, {column} as answer
            from fct_lgps_fund_year
            where fund_type = 'fund' and {column} is not null
        """).df()
        sample = candidates.sample(n=N_PER_SCALAR_TEMPLATE, random_state=qid)
        for _, row in sample.iterrows():
            questions.append({
                "id": qid,
                "question": template.format(fund=row["local_authority"], year=row["year"]),
                "expected_answer": float(row["answer"]),
                "unit": "GBP thousands" if "member" not in column and "employer" not in column and "pensioner" not in column else "count",
                "tolerance": "relative:0.01",
                "ground_truth_sql": (
                    f"select {column} from fct_lgps_fund_year "
                    f"where ecode = '{row['ecode']}' and year = '{row['year']}'"
                ),
            })
            qid += 1

    growth_candidates = con.sql("""
        select ecode, local_authority, year,
               market_value_end_of_year - market_value_start_of_year as growth
        from fct_lgps_fund_year
        where fund_type = 'fund'
          and market_value_end_of_year is not null
          and market_value_start_of_year is not null
    """).df()
    for _, row in growth_candidates.sample(n=N_GROWTH, random_state=999).iterrows():
        questions.append({
            "id": qid,
            "question": GROWTH_TEMPLATE.format(fund=row["local_authority"], year=row["year"]),
            "expected_answer": float(row["growth"]),
            "unit": "GBP thousands",
            "tolerance": "relative:0.01",
            "ground_truth_sql": (
                f"select market_value_end_of_year - market_value_start_of_year "
                f"from fct_lgps_fund_year where ecode = '{row['ecode']}' and year = '{row['year']}'"
            ),
        })
        qid += 1

    ranking_years = random.sample(years, k=min(N_RANKING, len(years)))
    for year in ranking_years:
        row = con.sql(f"""
            select local_authority, total_income
            from fct_lgps_fund_year
            where fund_type = 'fund' and year = '{year}' and total_income is not null
            order by total_income desc
            limit 1
        """).fetchone()
        questions.append({
            "id": qid,
            "question": RANKING_TEMPLATE.format(year=year),
            "expected_answer": row[0],
            "unit": "fund name",
            "tolerance": "exact_string",
            "ground_truth_sql": (
                f"select local_authority from fct_lgps_fund_year "
                f"where fund_type = 'fund' and year = '{year}' "
                f"order by total_income desc limit 1"
            ),
        })
        qid += 1

    OUT_PATH.write_text(json.dumps(questions, indent=2))
    print(f"Wrote {len(questions)} questions to {OUT_PATH}")


if __name__ == "__main__":
    main()

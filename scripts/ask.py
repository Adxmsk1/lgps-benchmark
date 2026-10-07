"""
Plain-English question box: turns a natural-language question into a SQL
query against fct_lgps_fund_year (via the Claude API) and runs it.

    python3 scripts/ask.py "What was Barnet's total expenditure in 2023-24?"

Requires ANTHROPIC_API_KEY (see .env.example).
"""

import os
import re
import sys

import duckdb
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "dev.duckdb"
MODEL = os.environ.get("ASK_MODEL", "claude-haiku-4-5-20251001")

SCHEMA_DESCRIPTION = """
Table: fct_lgps_fund_year
One row per Local Government Pension Scheme fund per financial year.
Money columns are in GBP thousands (£000s). Membership columns are headcounts.

Columns:
  ecode                        text    fund code
  local_authority              text    fund / local authority name
  year                          text    financial year, e.g. '2023-24'
  fund_type                     text    'fund' for an individual LGPS fund, 'national_total' for the England/Wales/England&Wales aggregate rows (ecodes E9999, W9999, EW001) -- exclude these from fund-level questions unless asked for a national total
  pension_benefits_paid        double  pensions paid to retired members and dependents
  lump_sums_retirement         double
  lump_sums_optional           double
  lump_sums_death               double
  other_benefits                double
  transfer_values_out           double
  pensions_act_premiums         double
  admin_and_mgmt_costs          double
  other_expenditure             double
  total_expenditure             double  sum of all expenditure items
  contributions_employees       double
  contributions_employers       double
  investment_income             double
  transfer_values_in            double
  other_income                   double
  total_income                   double  sum of all income items
  total_employers               double  number of employers in the fund
  total_contributing_members    double
  total_pensioners               double
  total_deferred_members         double
  total_members                  double
  market_value_start_of_year     double  fund assets at 1 April
  market_value_end_of_year       double  fund assets at 31 March
"""

SYSTEM_PROMPT = f"""You translate a plain-English question about UK Local \
Government Pension Scheme funds into a single DuckDB SQL query.

{SCHEMA_DESCRIPTION}

Rules:
- Output ONLY the SQL query. No markdown fences, no explanation.
- Use exactly one SELECT statement, reading only from fct_lgps_fund_year.
- Unless the question explicitly asks about a national total, filter to
  fund_type = 'fund'.
- Match fund names with ILIKE ('%name%') since names aren't always exact
  (e.g. official name vs. common name).
- If the question asks "which fund", return local_authority. If it asks
  "how much" or "how many", return a single numeric column.
"""

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|copy|pragma|export|install|load)\b",
    re.IGNORECASE,
)


def nl_to_sql(question: str, client: Anthropic) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}],
    )
    sql = response.content[0].text.strip()
    sql = re.sub(r"^```(sql)?|```$", "", sql.strip(), flags=re.MULTILINE).strip()
    return sql


def run_sql(sql: str, db_path: str = DB_PATH):
    stripped = sql.strip().rstrip(";")
    if not stripped.lower().startswith("select"):
        raise ValueError(f"Refusing to run non-SELECT SQL: {sql!r}")
    if FORBIDDEN.search(stripped):
        raise ValueError(f"Refusing to run SQL with a forbidden keyword: {sql!r}")
    con = duckdb.connect(db_path, read_only=True)
    return con.sql(stripped).df()


def answer_question(question: str, client: Anthropic | None = None) -> dict:
    client = client or Anthropic()
    sql = nl_to_sql(question, client)
    df = run_sql(sql)
    scalar = df.iloc[0, 0] if df.shape == (1, 1) else None
    return {"question": question, "sql": sql, "result": df, "scalar": scalar}


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/ask.py \"<question>\"")
        sys.exit(1)
    question = " ".join(sys.argv[1:])
    result = answer_question(question)
    print(f"SQL:\n  {result['sql']}\n")
    print("Result:")
    print(result["result"].to_string(index=False))


if __name__ == "__main__":
    main()

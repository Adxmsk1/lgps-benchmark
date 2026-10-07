# lgps-benchmark

Benchmarking every Local Government Pension Scheme (LGPS) fund in England and
Wales on costs, contributions, membership and asset growth over roughly ten
years, with a natural-language question box on top, built on dbt + DuckDB.

## The question

Every LGPS fund (Barnet's included) publishes the same annual return, but
comparing funds means pulling 9 years of spreadsheets that each lay the data
out slightly differently and reconciling them by hand. This project builds
that comparison once, as a pipeline, and tests whether a plain-English
question box on top of it can actually be trusted to answer correctly.

## The data

Source: the "Pension funds data table" spreadsheets (SF3 returns) published
in each year's "Local government pension scheme funds for England and Wales"
statistical release, from the
[LGPS statistics collection](https://www.gov.uk/government/collections/local-government-pension-scheme)
on gov.uk. Files are kept under their original names in `data/raw/` (not
committed to git — re-run the download to repopulate).

| Year | Release page | File |
|---|---|---|
| 2016 to 2017 | https://www.gov.uk/government/statistics/local-government-pension-scheme-funds-for-england-and-wales-2016-to-2017 | `LA_drop_down.xlsx` |
| 2017 to 2018 | https://www.gov.uk/government/statistics/local-government-pension-scheme-funds-for-england-and-wales-2017-to-2018 | `LA_drop_down_revised.xlsx` |
| 2018 to 2019 | https://www.gov.uk/government/statistics/local-government-pension-scheme-funds-for-england-and-wales-2018-to-2019 | `LA_drop_down_2018-19.xlsx` |
| 2019 to 2020 | https://www.gov.uk/government/statistics/local-government-pension-scheme-funds-for-england-and-wales-2019-to-2020 | `LA_drop_down_2019-20_revised.xlsx` |
| 2020 to 2021 | https://www.gov.uk/government/statistics/local-government-pension-scheme-funds-for-england-and-wales-2020-to-2021 | `LA_drop_down_2020-21_revised.xlsx` |
| 2021 to 2022 | https://www.gov.uk/government/statistics/local-government-pension-scheme-funds-for-england-and-wales-2021-to-2022 | `LA_drop_down_2021-22_April_update.xlsx` |
| 2022 to 2023 | https://www.gov.uk/government/statistics/local-government-pension-scheme-funds-for-england-and-wales-2022-to-2023 | `LA_drop_down_2022-23_-_ecomms_-_July_2024.xlsx` |
| 2023 to 2024 | https://www.gov.uk/government/statistics/local-government-pension-scheme-funds-for-england-and-wales-2023-to-2024 | `LA_drop_down_2023-24_-_June_2025_-_ecomms.xlsx` |
| 2024 to 2025 | https://www.gov.uk/government/statistics/local-government-pension-scheme-funds-for-england-and-wales-2024-to-2025 | `LA_drop_down_2024-25_-_ecomms.xlsx` |

## The method

```
data/raw/*.xlsx  --[scripts/ingest.py]-->  data/processed/lgps_sf3_tidy.parquet  --[dbt]-->  dev.duckdb  --[export]-->  data/processed/lgps_benchmark_for_powerbi.csv
```

1. **`scripts/ingest.py`** reconciles the 9 spreadsheets into one tidy
   `(ecode, local_authority, year, measure, value)` table. The files span
   two different layouts (2016-17 to 2022-23 vs. 2023-24 onwards), and even
   within one era the header row shifts up or down by a row between years.
   Rather than hardcode row/column numbers per year, the script locates each
   sheet's header by searching for the "Local Authority" cell and reads
   everything else relative to that.
2. **`dbt build`** loads the tidy parquet into DuckDB (`stg_sf3__tidy`),
   then pivots it into one row per fund per year with 23 measures as
   columns (`fct_lgps_fund_year`) — costs, contributions, membership and
   fund market value. Data tests check for unique fund-year keys, no
   negative fund values, and — the one that matters most — that summing
   every individual fund matches the *published* England & Wales total for
   every year and measure, within 0.1%.
3. The export step copies `fct_lgps_fund_year` to a flat CSV for Power BI,
   which can't read DuckDB's file format directly.

## The AI layer

`scripts/ask.py` turns a plain-English question into a SQL query against
`fct_lgps_fund_year`, using the Claude API (`claude-haiku-4-5`) with a
system prompt that describes the table's schema and requires the model to
output nothing but a single `SELECT` statement. The harness refuses to run
anything else (no `INSERT`/`DROP`/`ATTACH`/etc.) before executing it against
DuckDB.

```bash
python3 scripts/ask.py "What was Barnet's total expenditure in 2023-24?"
```

**The test**: `eval/build_eval_set.py` generates 50 questions by sampling
real funds, years and measures and computing each expected answer directly
from the data with plain SQL — independent of the AI layer, so the eval
can't just agree with whatever the model says. The questions span all four
benchmarking dimensions (costs, contributions, membership, asset growth)
plus a few ranking questions. `eval/run_eval.py` runs every question through
the AI layer and scores it against the known answer (exact match for fund
names, 1% relative tolerance for numbers).

## Results

**48/50 correct (96%)** — full breakdown in `eval/results.md`.

Both failures are genuine AI-layer limitations, not harness bugs:

- **Ambiguous fund names.** "By how much did the market value of *South
  Yorkshire Pensions Fund*'s fund grow during 2016-17?" — the model wrote
  `WHERE local_authority ILIKE '%South Yorkshire%'`, which also matches a
  *different* fund, "South Yorkshire PTA" (the Passenger Transport
  Authority's separate superannuation fund). The query returned two rows
  instead of one, even though the question gave the fund's full name. A
  stricter match (or a two-step "find the fund, then ask about it" prompt)
  would fix this.
- **Chain-of-thought leaking into the output.** On one question the model
  second-guessed its own first draft mid-response ("Wait, I need to correct
  this...") and that reasoning text ended up inside the SQL output, which
  then failed to parse. The system prompt says to output *only* SQL; a
  cheap, fast model doesn't always obey that under self-correction. Using a
  larger model, or asking for the SQL inside a fenced block and stripping
  everything else, would both help.

Neither is a case of the model getting the *arithmetic* wrong — in every
failure, the underlying DuckDB query was itself a reasonable (if overly
broad, or malformed) translation of the question. The risk this system
actually carries in practice is silent over-matching on fund names, not bad
maths.

## Setup

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your own Anthropic API key (needed
only for `scripts/ask.py` and `eval/run_eval.py`):

```bash
cp .env.example .env
# then edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

```bash
source .venv/bin/activate
export DBT_PROFILES_DIR=$(pwd)

python3 scripts/ingest.py   # data/raw/*.xlsx -> data/processed/lgps_sf3_tidy.parquet
dbt build                    # loads the parquet into dev.duckdb, builds models, runs tests
```

Export the final table for Power BI:

```bash
python3 -c "
import duckdb
duckdb.connect('dev.duckdb').sql('''
    COPY fct_lgps_fund_year TO 'data/processed/lgps_benchmark_for_powerbi.csv'
    (HEADER, DELIMITER ',')
''')
"
```

Ask a question, or re-run the eval:

```bash
python3 scripts/ask.py "Which fund had the highest total income in 2022-23?"
python3 eval/run_eval.py
```

Run the dashboard:

```bash
streamlit run dashboard/app.py
```

## The dashboard

A Python/Streamlit benchmarking dashboard, built as a second, publicly
deployable artifact alongside the Power BI one -- Power BI demonstrates the
tool used day to day in local government and finance; this one can actually
host the AI layer live rather than sitting next to it as a separate script.

Pick any of the 94 funds and it shows: fund value growth indexed against the
England & Wales average, where that fund ranks on admin cost per member
against every other fund, membership composition over time, and the nearest
funds by cost efficiency. The "Ask a question" box at the bottom is a
placeholder for now -- it answers a few example questions from the real
data, but isn't wired up to the live Claude-based layer in `scripts/ask.py`
yet. A public page that lets anyone trigger an LLM call on demand needs
rate-limiting and a hosted API key first, which is a deliberate follow-up
once this is ready to publish, not an oversight.

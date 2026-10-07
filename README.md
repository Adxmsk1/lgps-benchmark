# lgps-benchmark

Benchmarking every Local Government Pension Scheme (LGPS) fund in England and
Wales on costs, contributions, membership and asset growth over roughly ten
years, built on dbt + DuckDB.

## The question

Every LGPS fund publishes the same annual return, but comparing funds means
pulling 9 years of spreadsheets that each lay the data out slightly
differently and reconciling them by hand. This project builds that
comparison once, as a pipeline, and uses it to ask sector-wide questions a
single year's return can't answer on its own: is the sector still
cash-flow positive, is it maturing, and does fund size actually buy
efficiency.

## The data

Source: the "Pension funds data table" spreadsheets (SF3 returns) published
in each year's "Local government pension scheme funds for England and Wales"
statistical release, from the
[LGPS statistics collection](https://www.gov.uk/government/collections/local-government-pension-scheme)
on gov.uk. Files are kept under their original names in `data/raw/` (not
committed to git; re-run the download to repopulate).

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
   columns (`fct_lgps_fund_year`): costs, contributions, membership and
   fund market value. Data tests check for unique fund-year keys, no
   negative fund values, and, most importantly, that summing every
   individual fund matches the *published* England & Wales total for
   every year and measure, within 0.1%.
3. The export step copies `fct_lgps_fund_year` to a flat CSV for Power BI,
   which can't read DuckDB's file format directly.

## The dashboard

A Python/Streamlit dashboard, built as a second artifact alongside the
Power BI one: Power BI demonstrates the tool used day to day in local
government and finance, while this one can be published as a public,
standalone web page.

It opens on a sector-wide view (no single fund drives it), built around
four descriptive questions:

- **Total sector assets**: nominal growth over the 9 years, £258.8bn to
  £402.3bn (+55%).
- **Contributions vs. benefits paid**: the sector's net cash flow. Roughly
  balanced in 2016-17 (£9.5bn each); by 2024-25 benefits paid (£15.4bn)
  outstrips contributions (£13.3bn) by about £2bn a year, a scheme
  maturing into net outflow.
- **Sector membership composition**: pensioners grew 36% over the period
  against 10% for contributing members, the same maturing signal from the
  membership side.
- **Does fund size buy efficiency?**: admin cost per member plotted
  against fund size across all 87 funds. The correlation is -0.19: bigger
  funds aren't meaningfully cheaper to run per member.

A fund can still be highlighted on the scale chart for anyone who wants to
find their own council, but it's an optional overlay, not the default view.

It reads `dashboard/data.csv`, a small (174KB) export of `fct_lgps_fund_year`
checked into the repo for this purpose, so it runs standalone: no need to
build the full pipeline first, and it deploys as-is on Streamlit Community
Cloud straight from GitHub.

## Setup

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
```

## Usage

Run the dashboard on its own (no setup beyond `pip install`, it reads the
bundled `dashboard/data.csv`):

```bash
source .venv/bin/activate
streamlit run dashboard/app.py
```

Rebuild the full pipeline from source:

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

Refresh the dashboard's bundled data after a pipeline rebuild:

```bash
python3 -c "
import duckdb
duckdb.connect('dev.duckdb').sql('''
    COPY fct_lgps_fund_year TO 'dashboard/data.csv' (HEADER, DELIMITER ',')
''')
"
```

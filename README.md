# lgps-benchmark

Benchmarking every Local Government Pension Scheme (LGPS) fund in England and
Wales on costs, contributions, membership and asset growth over roughly ten
years, built on dbt + DuckDB.

## Setup

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
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

## Data

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

## Pipeline

```
data/raw/*.xlsx  --[scripts/ingest.py]-->  data/processed/lgps_sf3_tidy.parquet  --[dbt]-->  dev.duckdb  --[export]-->  data/processed/lgps_benchmark_for_powerbi.csv
```

1. **`scripts/ingest.py`** reconciles the 9 spreadsheets, each laid out
   slightly differently, into one tidy `(ecode, local_authority, year,
   measure, value)` table. It locates each sheet's header row by searching
   for the "Local Authority" cell rather than assuming a fixed row number,
   since that row shifts between years.
2. **`dbt build`** loads the tidy parquet into DuckDB (`stg_sf3__tidy`),
   then pivots it into one row per fund per year with 23 measures as
   columns (`fct_lgps_fund_year`) — costs, contributions, membership and
   fund market value. Data tests check for unique fund-year keys, no
   negative fund values, and that summing every individual fund matches
   the published England & Wales total for each year/measure.
3. The export step copies `fct_lgps_fund_year` out to a flat CSV for Power
   BI, which can't read DuckDB's file format directly.

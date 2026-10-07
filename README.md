# lgps-benchmark

dbt + DuckDB project.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
source .venv/bin/activate
export DBT_PROFILES_DIR=$(pwd)
dbt debug
dbt run
dbt test
```

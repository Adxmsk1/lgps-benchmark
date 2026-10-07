-- dbt test: fails if this returns any rows (negative fund value)

select ecode, local_authority, year, market_value_start_of_year, market_value_end_of_year
from {{ ref('fct_lgps_fund_year') }}
where market_value_start_of_year < 0
   or market_value_end_of_year < 0

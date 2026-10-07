-- dbt test: fails if fund totals don't sum to the published EW001 total, within tolerance

with fund_totals as (
    select year, measure, sum(value) as summed_value
    from {{ ref('stg_sf3__tidy') }}
    where fund_type = 'fund'
    group by year, measure
),

published_totals as (
    select year, measure, value as published_value
    from {{ ref('stg_sf3__tidy') }}
    where ecode = 'EW001'
)

select
    f.year,
    f.measure,
    f.summed_value,
    p.published_value,
    f.summed_value - p.published_value as difference
from fund_totals f
join published_totals p using (year, measure)
where abs(f.summed_value - p.published_value) > greatest(1, abs(p.published_value) * 0.001)

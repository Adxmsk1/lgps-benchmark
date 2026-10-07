-- Raw tidy (ecode, local_authority, year, measure, value) rows produced by
-- scripts/ingest.py, with aggregate rows (England, Wales, England & Wales)
-- flagged separately from individual fund rows.

select
    ecode,
    -- Strip trailing footnote/revision markers like "[note a]" or "(R)":
    -- the same fund's name sometimes carries one in one sheet (e.g. the
    -- Exp & Income return) but not another (e.g. the membership return)
    -- within the same year, which would otherwise split one fund into two
    -- rows once pivoted.
    trim(regexp_replace(local_authority, '\s*[\[\(][^\]\)]*[\]\)]\s*$', '')) as local_authority,
    year,
    measure,
    value,
    case
        when ecode in ('E9999', 'W9999', 'EW001') then 'national_total'
        else 'fund'
    end as fund_type
from read_parquet('data/processed/lgps_sf3_tidy.parquet')

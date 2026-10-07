-- Output of scripts/ingest.py. National-total rows flagged separately below.

select
    ecode,
    -- strip footnote markers like "[note a]" or "(R)", which some sheets attach to a fund name and others don't
    trim(regexp_replace(local_authority, '\s*[\[\(][^\]\)]*[\]\)]\s*$', '')) as local_authority,
    year,
    measure,
    value,
    case
        when ecode in ('E9999', 'W9999', 'EW001') then 'national_total'
        else 'fund'
    end as fund_type
from read_parquet('data/processed/lgps_sf3_tidy.parquet')

-- One row per fund per year, measures pivoted into columns. £ figures in £000s.

select
    ecode || '_' || year as fund_year_key,
    ecode,
    local_authority,
    year,
    fund_type,

    -- costs (expenditure), £000s
    max(case when measure = 'pension' then value end) as pension_benefits_paid,
    max(case when measure = 'lump_retire' then value end) as lump_sums_retirement,
    max(case when measure = 'lump_opt' then value end) as lump_sums_optional,
    max(case when measure = 'lump_death' then value end) as lump_sums_death,
    max(case when measure = 'othben' then value end) as other_benefits,
    max(case when measure = 'transf_out' then value end) as transfer_values_out,
    max(case when measure = 'penprem' then value end) as pensions_act_premiums,
    max(case when measure = 'mgmtexp' then value end) as admin_and_mgmt_costs,
    max(case when measure = 'othexp' then value end) as other_expenditure,
    max(case when measure = 'totpens_exp' then value end) as total_expenditure,

    -- contributions and income, £000s
    max(case when measure = 'contrib_empee' then value end) as contributions_employees,
    max(case when measure = 'contrib_emper' then value end) as contributions_employers,
    max(case when measure = 'invinc' then value end) as investment_income,
    max(case when measure = 'transf_in' then value end) as transfer_values_in,
    max(case when measure = 'othinc' then value end) as other_income,
    max(case when measure = 'totpens_inc' then value end) as total_income,

    -- membership, headcount
    max(case when measure = 'empler_tot' then value end) as total_employers,
    max(case when measure = 'contmem_tot' then value end) as total_contributing_members,
    max(case when measure = 'pensioner_tot' then value end) as total_pensioners,
    max(case when measure = 'defmemb_tot' then value end) as total_deferred_members,
    max(case when measure = 'totmember_tot' then value end) as total_members,

    -- fund assets, £000s
    max(case when measure = 'mktval_startyr' then value end) as market_value_start_of_year,
    max(case when measure = 'mktval_endyr' then value end) as market_value_end_of_year

from {{ ref('stg_sf3__tidy') }}
group by ecode, local_authority, year, fund_type

"""
LGPS sector benchmarking dashboard.

    streamlit run dashboard/app.py

Reads fct_lgps_fund_year from dev.duckdb (built by `dbt build` -- see
README.md). Sector-wide descriptive analysis first; a single fund can be
highlighted on the scale chart, but no fund drives the default view.
"""

from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DB_PATH = Path(__file__).resolve().parent.parent / "dev.duckdb"

ACCENT = "#A3661F"
ACCENT2 = "#2F5C55"
GOOD = "#3F6E46"
BAD = "#9A3B28"
MUTED = "#8C96A0"
GRID = "#E3DCCB"
GAP_FILL = "rgba(154,59,40,0.10)"

st.set_page_config(page_title="LGPS fund benchmarking", page_icon="📊", layout="wide")

st.markdown("""
<style>
.kpi-card{background:#FBF8F1;border:1px solid #E3DCCB;border-radius:10px;padding:14px 18px;}
.kpi-label{font-size:12px;color:#5B6B78;margin:0 0 6px;}
.kpi-value{font-size:26px;font-weight:600;margin:0;font-family:ui-monospace,monospace;}
.kpi-sub{font-size:12px;margin-top:6px;}
.flag{display:inline-block;font-size:11px;font-weight:600;padding:2px 8px;border-radius:5px;}
.flag-bad{background:#F3E1D9;color:#9A3B28;}
.flag-good{background:#E3EDE1;color:#3F6E46;}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_con():
    return duckdb.connect(str(DB_PATH), read_only=True)


@st.cache_data
def load_fund_list() -> pd.DataFrame:
    return get_con().sql("""
        select distinct ecode, local_authority
        from fct_lgps_fund_year where fund_type = 'fund'
        order by local_authority
    """).df()


@st.cache_data
def load_sector_by_year() -> pd.DataFrame:
    return get_con().sql("""
        select
            year,
            count(*) as n_funds,
            sum(market_value_end_of_year) as total_assets,
            sum(total_members) as total_members,
            sum(total_contributing_members) as total_contributing,
            sum(total_pensioners) as total_pensioners,
            sum(total_deferred_members) as total_deferred,
            sum(contributions_employees + contributions_employers) as total_contributions,
            sum(pension_benefits_paid + lump_sums_retirement + lump_sums_optional
                + lump_sums_death + other_benefits) as benefits_paid
        from fct_lgps_fund_year
        where fund_type = 'fund'
        group by year order by year
    """).df()


@st.cache_data
def load_cost_scale(year: str) -> pd.DataFrame:
    return get_con().execute("""
        select ecode, local_authority, total_members, admin_and_mgmt_costs,
               admin_and_mgmt_costs * 1000.0 / total_members as cost_per_member
        from fct_lgps_fund_year
        where fund_type = 'fund' and year = ? and total_members > 0
          and admin_and_mgmt_costs is not null
        order by cost_per_member
    """, [year]).df()


@st.cache_data
def load_concentration(year: str) -> float:
    con = get_con()
    top10 = con.execute("""
        select sum(market_value_end_of_year) from (
            select market_value_end_of_year from fct_lgps_fund_year
            where fund_type = 'fund' and year = ?
            order by market_value_end_of_year desc limit 10
        )
    """, [year]).fetchone()[0]
    total = con.execute("""
        select sum(market_value_end_of_year) from fct_lgps_fund_year
        where fund_type = 'fund' and year = ?
    """, [year]).fetchone()[0]
    return top10 / total * 100


sector = load_sector_by_year()
funds = load_fund_list()
first, latest = sector.iloc[0], sector.iloc[-1]
latest_year = latest["year"]

cpm = load_cost_scale(latest_year)
corr = cpm[["total_members", "cost_per_member"]].corr().iloc[0, 1]
top10_share = load_concentration(latest_year)

assets_growth = (latest.total_assets / first.total_assets - 1) * 100
members_growth = (latest.total_members / first.total_members - 1) * 100
net_flow = latest.total_contributions - latest.benefits_paid

st.title("LGPS fund benchmarking")
st.caption(f"{int(latest.n_funds)} England & Wales pension funds, {first.year} to {latest_year} · source: gov.uk SF3 returns")

hl_l, hl_r = st.columns([3, 1])
with hl_r:
    highlight = st.selectbox("Highlight a fund (optional)", ["None"] + list(funds.local_authority))

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f"""<div class="kpi-card"><p class="kpi-label">Total sector assets, {latest_year}</p>
        <p class="kpi-value">£{latest.total_assets/1e6:,.0f}bn</p>
        <p class="kpi-sub" style="color:{GOOD};">↑ {assets_growth:.0f}% since {first.year}</p></div>""", unsafe_allow_html=True)
with k2:
    st.markdown(f"""<div class="kpi-card"><p class="kpi-label">Total members, {latest_year}</p>
        <p class="kpi-value">{latest.total_members/1e6:,.2f}m</p>
        <p class="kpi-sub" style="color:{GOOD};">↑ {members_growth:.0f}% since {first.year}</p></div>""", unsafe_allow_html=True)
with k3:
    flow_flag = "flag-bad" if net_flow < 0 else "flag-good"
    flow_label = "cash-flow negative" if net_flow < 0 else "cash-flow positive"
    flow_sign = "-" if net_flow < 0 else ""
    st.markdown(f"""<div class="kpi-card"><p class="kpi-label">Contributions &minus; benefits paid</p>
        <p class="kpi-value">{flow_sign}£{abs(net_flow)/1e3:,.0f}m</p>
        <p class="kpi-sub"><span class="flag {flow_flag}">{flow_label}</span></p></div>""", unsafe_allow_html=True)
with k4:
    st.markdown(f"""<div class="kpi-card"><p class="kpi-label">Funds in the sector</p>
        <p class="kpi-value">{int(latest.n_funds)}</p>
        <p class="kpi-sub" style="color:{MUTED};">down from {int(first.n_funds)} in {first.year} (mergers)</p></div>""", unsafe_allow_html=True)

st.write("")
c1, c2 = st.columns(2)

with c1:
    st.subheader("Total sector assets")
    st.caption("Sum of fund value at year end, all funds, £bn nominal")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sector["year"], y=sector["total_assets"] / 1e6,
        line=dict(color=ACCENT, width=2.5), fill="tozeroy",
        fillcolor="rgba(163,102,31,0.08)", mode="lines+markers",
        marker=dict(size=5),
    ))
    fig.update_layout(
        height=270, margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
        plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor=GRID, title="£bn", rangemode="tozero"),
        font=dict(color="#1C2B3A"),
    )
    st.plotly_chart(fig, width="stretch")

with c2:
    st.subheader("Contributions vs. benefits paid")
    st.caption("The sector's net cash flow -- a widening gap means a maturing scheme")
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=sector["year"], y=sector["total_contributions"] / 1e3,
        name="Contributions received", line=dict(color=ACCENT2, width=2.5), mode="lines",
    ))
    fig2.add_trace(go.Scatter(
        x=sector["year"], y=sector["benefits_paid"] / 1e3,
        name="Benefits paid", line=dict(color=BAD, width=2.5), mode="lines",
        fill="tonexty", fillcolor=GAP_FILL,
    ))
    fig2.update_layout(
        height=270, margin=dict(l=0, r=0, t=10, b=0),
        plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor=GRID, title="£bn"),
        legend=dict(orientation="h", yanchor="bottom", y=-0.3, x=0),
        font=dict(color="#1C2B3A"),
    )
    st.plotly_chart(fig2, width="stretch")

st.write("")
c3, c4 = st.columns(2)

with c3:
    st.subheader("Sector membership composition")
    st.caption("Contributing members, pensioners and deferred members, summed across all funds")
    fig3 = go.Figure()
    for col, label, color in [
        ("total_contributing", "Contributing", ACCENT),
        ("total_pensioners", "Pensioners", ACCENT2),
        ("total_deferred", "Deferred", GOOD),
    ]:
        fig3.add_trace(go.Scatter(
            x=sector["year"], y=sector[col] / 1e6, name=label, mode="lines",
            stackgroup="one", line=dict(width=0.5, color=color),
        ))
    fig3.update_layout(
        height=270, margin=dict(l=0, r=0, t=10, b=0),
        plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor=GRID, title="Members (m)"),
        legend=dict(orientation="h", yanchor="bottom", y=-0.3, x=0),
        font=dict(color="#1C2B3A"),
    )
    st.plotly_chart(fig3, width="stretch")

with c4:
    st.subheader("Does fund size buy efficiency?")
    st.caption(f"Admin cost per member vs. fund size, {latest_year} · correlation {corr:+.2f} (weak)")
    fig4 = go.Figure()
    is_hl = cpm["local_authority"] == highlight
    fig4.add_trace(go.Scatter(
        x=cpm.loc[~is_hl, "total_members"], y=cpm.loc[~is_hl, "cost_per_member"],
        mode="markers", marker=dict(color=MUTED, size=8, opacity=0.5),
        hovertext=cpm.loc[~is_hl, "local_authority"], hoverinfo="text", name="Funds",
    ))
    if highlight != "None" and is_hl.any():
        fig4.add_trace(go.Scatter(
            x=cpm.loc[is_hl, "total_members"], y=cpm.loc[is_hl, "cost_per_member"],
            mode="markers", marker=dict(color=ACCENT, size=15, line=dict(color="white", width=2)),
            hovertext=cpm.loc[is_hl, "local_authority"], hoverinfo="text", name=highlight,
        ))
    fig4.update_layout(
        height=270, margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
        plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor=GRID, title="Members (log scale)", type="log"),
        yaxis=dict(gridcolor=GRID, title="£ per member"),
        font=dict(color="#1C2B3A"),
    )
    st.plotly_chart(fig4, width="stretch")

st.write("")
t1, t2 = st.columns(2)
with t1:
    st.subheader("Lowest cost per member")
    cheap = cpm.head(5)[["local_authority", "total_members", "cost_per_member"]].copy()
    cheap.columns = ["Fund", "Members", "Cost / member"]
    cheap["Members"] = cheap["Members"].map("{:,.0f}".format)
    cheap["Cost / member"] = cheap["Cost / member"].map("£{:,.0f}".format)
    st.dataframe(cheap, hide_index=True, width="stretch")
with t2:
    st.subheader("Highest cost per member")
    pricey = cpm.tail(5)[["local_authority", "total_members", "cost_per_member"]].iloc[::-1].copy()
    pricey.columns = ["Fund", "Members", "Cost / member"]
    pricey["Members"] = pricey["Members"].map("{:,.0f}".format)
    pricey["Cost / member"] = pricey["Cost / member"].map("£{:,.0f}".format)
    st.dataframe(pricey, hide_index=True, width="stretch")

st.caption(f"The 10 largest funds hold {top10_share:.0f}% of total sector assets ({latest_year}) · source: gov.uk LGPS SF3 returns, {first.year} to {latest_year}")

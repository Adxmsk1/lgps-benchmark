"""LGPS sector benchmarking dashboard. Run with: streamlit run dashboard/app.py"""

from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DATA_PATH = Path(__file__).resolve().parent / "data.csv"

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
.insight{background:#FBF8F1;border:1px solid #E3DCCB;border-left:3px solid #A3661F;
  border-radius:0 8px 8px 0;padding:10px 16px;margin:8px 0 4px;font-size:13.5px;
  line-height:1.55;color:#1C2B3A;}
.insight b{color:#8A5518;}
</style>
""", unsafe_allow_html=True)


def insight(text):
    st.markdown(f'<div class="insight"><b>Reading this:</b> {text}</div>', unsafe_allow_html=True)


@st.cache_resource
def get_con():
    con = duckdb.connect(":memory:")
    con.sql(f"create table fct_lgps_fund_year as select * from read_csv_auto('{DATA_PATH}')")
    return con


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
def load_fund_history(ecode: str) -> pd.DataFrame:
    df = get_con().execute("""
        select year, market_value_end_of_year, total_members, admin_and_mgmt_costs,
               contributions_employees + contributions_employers as contributions,
               pension_benefits_paid + lump_sums_retirement + lump_sums_optional
                   + lump_sums_death + other_benefits as benefits_paid,
               total_contributing_members, total_pensioners, total_deferred_members
        from fct_lgps_fund_year where ecode = ? order by year
    """, [ecode]).df()
    df["cost_per_member"] = df.admin_and_mgmt_costs * 1000.0 / df.total_members
    return df


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


sector_all = load_sector_by_year()
funds = load_fund_list()
all_years = sector_all["year"].tolist()

st.title("LGPS fund benchmarking")
st.caption(f"{int(sector_all.iloc[-1].n_funds)} England & Wales pension funds, {all_years[0]} to {all_years[-1]} · source: gov.uk SF3 returns")

rng_col, hl_col = st.columns([3, 1])
with rng_col:
    year_range = st.select_slider("Year range", options=all_years, value=(all_years[0], all_years[-1]))
with hl_col:
    highlight = st.selectbox("Highlight a fund (optional)", ["None"] + list(funds.local_authority))

start_i, end_i = all_years.index(year_range[0]), all_years.index(year_range[1])
sector = sector_all.iloc[start_i:end_i + 1].reset_index(drop=True)
first, latest = sector.iloc[0], sector.iloc[-1]
snapshot_year = latest["year"]

cpm = load_cost_scale(snapshot_year)
corr = cpm[["total_members", "cost_per_member"]].corr().iloc[0, 1]
top10_share = load_concentration(snapshot_year)

assets_growth = (latest.total_assets / first.total_assets - 1) * 100
members_growth = (latest.total_members / first.total_members - 1) * 100
net_flow = latest.total_contributions - latest.benefits_paid
net_flow_first = first.total_contributions - first.benefits_paid

sector["assets_pct_change"] = sector["total_assets"].pct_change() * 100
pensioner_growth = (latest.total_pensioners / first.total_pensioners - 1) * 100
contributing_growth = (latest.total_contributing / first.total_contributing - 1) * 100

def flow_desc(value_000s):
    sign = "shortfall" if value_000s < 0 else "surplus"
    return f"£{abs(value_000s)/1e3:,.0f}m {sign}"


fund_growth = fund_hist = None
fund_net_flow = fund_rank = fund_cpm = None
fund_pens_growth = fund_contrib_growth = None
if highlight != "None":
    ecode = funds.loc[funds.local_authority == highlight, "ecode"].iloc[0]
    fund_hist_all = load_fund_history(ecode)
    fund_hist = fund_hist_all[fund_hist_all.year.isin(sector["year"])].reset_index(drop=True)

    if len(fund_hist) >= 2 and fund_hist.iloc[0].market_value_end_of_year:
        fh0, fh1 = fund_hist.iloc[0], fund_hist.iloc[-1]
        fund_growth = (fh1.market_value_end_of_year / fh0.market_value_end_of_year - 1) * 100
        if fh0.total_pensioners and fh0.total_contributing_members:
            fund_pens_growth = (fh1.total_pensioners / fh0.total_pensioners - 1) * 100
            fund_contrib_growth = (fh1.total_contributing_members / fh0.total_contributing_members - 1) * 100

    if len(fund_hist) >= 1:
        fund_net_flow = fund_hist.iloc[-1].contributions - fund_hist.iloc[-1].benefits_paid

    is_hl_row = cpm["local_authority"] == highlight
    if is_hl_row.any():
        fund_rank = int(cpm.reset_index(drop=True).index[is_hl_row][0]) + 1
        fund_cpm = cpm.loc[is_hl_row, "cost_per_member"].iloc[0]

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f"""<div class="kpi-card"><p class="kpi-label">Total sector assets, {snapshot_year}</p>
        <p class="kpi-value">£{latest.total_assets/1e6:,.0f}bn</p>
        <p class="kpi-sub" style="color:{GOOD};">↑ {assets_growth:.0f}% since {first.year}</p></div>""", unsafe_allow_html=True)
with k2:
    st.markdown(f"""<div class="kpi-card"><p class="kpi-label">Total members, {snapshot_year}</p>
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
    if highlight == "None":
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
        if len(sector) >= 3:
            worst_year = sector.loc[sector["assets_pct_change"].idxmin()]
            best_year = sector.loc[sector["assets_pct_change"].idxmax()]
            insight(
                f"Growth isn't smooth. Assets fell {abs(worst_year.assets_pct_change):.0f}% in "
                f"{worst_year.year}, the valuation date that landed right in the COVID market "
                f"drawdown, then jumped {best_year.assets_pct_change:.0f}% the following year as "
                f"markets recovered. LGPS funds hold meaningful bond and equity allocations, so "
                f"these are valuation swings, not sudden changes in membership or contributions."
            )
        else:
            insight(
                f"Total sector assets grew {assets_growth:.0f}% from {first.year} to "
                f"{snapshot_year}. Widen the year range above to see how uneven that "
                f"growth has actually been year to year."
            )
    else:
        st.subheader(f"{highlight} vs. the sector average")
        st.caption(f"Fund value, indexed to {first.year} = 100, so size doesn't distort the comparison")
        if fund_hist is not None and len(fund_hist) >= 2 and fund_growth is not None:
            base = fund_hist.iloc[0].market_value_end_of_year
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=fund_hist["year"], y=fund_hist["market_value_end_of_year"] / base * 100,
                name=highlight, line=dict(color=ACCENT, width=2.5), mode="lines",
            ))
            fig.add_trace(go.Scatter(
                x=sector["year"], y=sector["total_assets"] / first.total_assets * 100,
                name="Sector average", line=dict(color=ACCENT2, width=2, dash="dash"), mode="lines",
            ))
            fig.update_layout(
                height=270, margin=dict(l=0, r=0, t=10, b=0),
                plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=False), yaxis=dict(gridcolor=GRID, title="Index"),
                legend=dict(orientation="h", yanchor="bottom", y=-0.3, x=0),
                font=dict(color="#1C2B3A"),
            )
            st.plotly_chart(fig, width="stretch")
            ahead_behind = "ahead of" if fund_growth > assets_growth else "behind"
            insight(
                f"{highlight}'s fund value grew {fund_growth:.0f}% over this period against "
                f"{assets_growth:.0f}% for the sector average: {ahead_behind} the broader "
                f"trend. Indexing both to the same base strips out the effect of fund size, "
                f"so this compares growth rates, not the underlying asset values."
            )
        else:
            st.info(f"No data for {highlight} across this year range.")

with c2:
    st.subheader("Contributions vs. benefits paid")
    st.caption("The sector's net cash flow: a widening gap means a maturing scheme")
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
    if first.year == snapshot_year:
        sector_line = f"In {snapshot_year}, the sector ran a {flow_desc(net_flow)}."
    else:
        sector_line = (
            f"The sector ran a {flow_desc(net_flow_first)} in {first.year} and a "
            f"{flow_desc(net_flow)} by {snapshot_year}."
        )
    fund_line = ""
    if highlight != "None" and fund_net_flow is not None:
        fund_line = f" {highlight} itself ran a {flow_desc(fund_net_flow)} in {snapshot_year}."
    insight(
        f"{sector_line} Running a net cash outflow doesn't mean a fund is underfunded, "
        f"investment income and asset sales can cover the gap, and LGPS funding levels "
        f"are judged at triennial valuation, not on this chart. It does mean a rising "
        f"reliance on investment returns to pay pensions, which raises the bar for "
        f"those returns.{fund_line}"
    )

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
    fund_member_line = ""
    if highlight != "None" and fund_pens_growth is not None:
        fund_member_line = (
            f" {highlight}'s own mix moved similarly: pensioners {fund_pens_growth:+.0f}% "
            f"against {fund_contrib_growth:+.0f}% for contributing members."
        )
    insight(
        f"Pensioners grew {pensioner_growth:.0f}% over the period against {contributing_growth:.0f}% "
        f"for contributing members: the scheme is ageing. Fewer active members are paying "
        f"in relative to the number now drawing a pension, which is the membership-side "
        f"mirror of the widening cash-flow gap on the left, and the reason behind the "
        f"sector's longer-term shift toward income-generating and liability-matching "
        f"assets over growth-seeking ones.{fund_member_line}"
    )

with c4:
    st.subheader("Does fund size buy efficiency?")
    st.caption(f"Admin cost per member vs. fund size, {snapshot_year} · correlation {corr:+.2f} (weak)")
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
    corr_strength = "no" if abs(corr) < 0.2 else ("a weak" if abs(corr) < 0.4 else "a moderate")
    fund_rank_line = ""
    if highlight != "None" and fund_rank is not None:
        fund_rank_line = (
            f"{highlight} sits at rank {fund_rank} of {len(cpm)} on this measure in "
            f"{snapshot_year}, at £{fund_cpm:,.0f} per member. "
        )
    insight(
        f"{fund_rank_line}Across the sector there's {corr_strength} relationship between "
        f"fund size and cost per member (correlation {corr:+.2f}). This is administration "
        f"cost specifically, running payroll, record-keeping, member queries, not "
        f"investment management, where scale economies are better documented. That "
        f"distinction is why England and Wales pooled LGPS investment management into "
        f"vehicles like Border to Coast and Brunel rather than merging the funds "
        f"themselves."
    )

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

st.caption(f"The 10 largest funds hold {top10_share:.0f}% of total sector assets ({snapshot_year}) · source: gov.uk LGPS SF3 returns, {first.year} to {snapshot_year}")

"""
LGPS fund benchmarking dashboard.

    streamlit run dashboard/app.py

Reads fct_lgps_fund_year from dev.duckdb (built by `dbt build` -- see
README.md). The question box at the bottom is a placeholder: it answers a
handful of example questions from the real data, but isn't yet wired up to
the live Claude-based question-to-SQL layer in scripts/ask.py -- that needs
rate-limiting and a hosted API key before it's safe to expose publicly, and
is a follow-up once this is published.
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
.ai-box{background:#FBF8F1;border:1px solid #E3DCCB;border-radius:10px;padding:16px 20px;margin-top:8px;}
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
def load_fund_history(ecode: str) -> pd.DataFrame:
    return get_con().execute(
        "select * from fct_lgps_fund_year where ecode = ? order by year", [ecode]
    ).df()


@st.cache_data
def load_ew_history() -> pd.DataFrame:
    return get_con().sql("""
        select year, market_value_end_of_year
        from fct_lgps_fund_year where ecode = 'EW001' order by year
    """).df()


@st.cache_data
def load_cost_per_member(year: str) -> pd.DataFrame:
    return get_con().execute("""
        select ecode, local_authority, total_members, admin_and_mgmt_costs,
               admin_and_mgmt_costs * 1000.0 / total_members as cost_per_member
        from fct_lgps_fund_year
        where fund_type = 'fund' and year = ? and total_members > 0
          and admin_and_mgmt_costs is not null
        order by cost_per_member
    """, [year]).df()


funds = load_fund_list()
default_idx = int(funds.index[funds.local_authority == "Barnet"][0]) if (funds.local_authority == "Barnet").any() else 0

st.title("LGPS fund benchmarking")

top_l, top_r = st.columns([3, 1])
with top_l:
    fund_name = st.selectbox("Fund", funds.local_authority, index=default_idx)
ecode = funds.loc[funds.local_authority == fund_name, "ecode"].iloc[0]

hist = load_fund_history(ecode)
latest = hist.iloc[-1]
latest_year = latest["year"]
ew = load_ew_history()
cpm = load_cost_per_member(latest_year)

rank = int(cpm.reset_index(drop=True).index[cpm.ecode == ecode][0]) + 1
n_funds = len(cpm)
cost_per_member = cpm.loc[cpm.ecode == ecode, "cost_per_member"].iloc[0]
high_cost = rank > n_funds * 0.6

growth_pct = (latest["market_value_end_of_year"] / hist.iloc[0]["market_value_end_of_year"] - 1) * 100

with top_r:
    st.markdown(f"<div style='text-align:right; color:{MUTED}; font-size:13px; padding-top:28px;'>Latest year: {latest_year}</div>", unsafe_allow_html=True)

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f"""<div class="kpi-card"><p class="kpi-label">Total members, {latest_year}</p>
        <p class="kpi-value">{latest['total_members']:,.0f}</p>
        <p class="kpi-sub" style="color:{MUTED};">{latest['total_contributing_members']:,.0f} contributing · {latest['total_pensioners']:,.0f} pensioners</p></div>""", unsafe_allow_html=True)
with k2:
    st.markdown(f"""<div class="kpi-card"><p class="kpi-label">Fund value, end of {latest_year}</p>
        <p class="kpi-value">£{latest['market_value_end_of_year']/1e6:,.2f}bn</p>
        <p class="kpi-sub" style="color:{GOOD if growth_pct >= 0 else BAD};">{'↑' if growth_pct >= 0 else '↓'} {abs(growth_pct):.0f}% since {hist.iloc[0]['year']}</p></div>""", unsafe_allow_html=True)
with k3:
    st.markdown(f"""<div class="kpi-card"><p class="kpi-label">Total expenditure, {latest_year}</p>
        <p class="kpi-value">£{latest['total_expenditure']/1e3:,.1f}m</p>
        <p class="kpi-sub" style="color:{MUTED};">vs £{latest['total_income']/1e3:,.1f}m income</p></div>""", unsafe_allow_html=True)
with k4:
    flag_class = "flag-bad" if high_cost else "flag-good"
    st.markdown(f"""<div class="kpi-card"><p class="kpi-label">Admin cost per member</p>
        <p class="kpi-value">£{cost_per_member:,.0f}</p>
        <p class="kpi-sub"><span class="flag {flag_class}">{rank} of {n_funds} funds</span></p></div>""", unsafe_allow_html=True)

st.write("")
c1, c2 = st.columns([1.15, 0.85])

with c1:
    st.subheader("Fund value growth vs. the England & Wales average")
    st.caption(f"Indexed to {hist.iloc[0]['year']} = 100, so fund size doesn't distort the comparison")

    base_year = hist.iloc[0]["year"]
    base_value = hist.iloc[0]["market_value_end_of_year"]
    ew_base = ew.loc[ew.year == base_year, "market_value_end_of_year"].iloc[0]
    ew_aligned = ew[ew.year >= base_year]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=hist["year"], y=hist["market_value_end_of_year"] / base_value * 100,
        name=fund_name, line=dict(color=ACCENT, width=2.5), mode="lines",
    ))
    fig.add_trace(go.Scatter(
        x=ew_aligned["year"], y=ew_aligned["market_value_end_of_year"] / ew_base * 100,
        name="England & Wales average", line=dict(color=ACCENT2, width=2, dash="dash"), mode="lines",
    ))
    fig.update_layout(
        height=280, margin=dict(l=0, r=0, t=10, b=0),
        plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor=GRID, title="Index"),
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, x=0),
        font=dict(color="#1C2B3A"),
    )
    st.plotly_chart(fig, width="stretch")

with c2:
    st.subheader(f"Admin cost per member, {latest_year}")
    st.caption(f"{fund_name} against all {n_funds} funds, lowest to highest cost")

    median_cost = cpm["cost_per_member"].median()
    fig2 = go.Figure()
    others = cpm[cpm.ecode != ecode]
    fig2.add_trace(go.Scatter(
        x=others["cost_per_member"], y=[0] * len(others), mode="markers",
        marker=dict(color=MUTED, size=8, opacity=0.5), name="Other funds",
        hovertext=others["local_authority"], hoverinfo="text",
    ))
    fig2.add_trace(go.Scatter(
        x=[cost_per_member], y=[0], mode="markers",
        marker=dict(color=ACCENT, size=16, line=dict(color="white", width=2)),
        name=fund_name, hovertext=[fund_name], hoverinfo="text",
    ))
    fig2.add_vline(x=median_cost, line=dict(color="#5B6B78", width=1, dash="dot"))
    fig2.add_annotation(x=median_cost, y=0.35, text=f"Median £{median_cost:,.0f}", showarrow=False, font=dict(size=11, color="#5B6B78"))
    fig2.add_annotation(x=cost_per_member, y=-0.35, text=f"{fund_name} £{cost_per_member:,.0f}", showarrow=False, font=dict(size=11, color=ACCENT))
    fig2.update_layout(
        height=280, margin=dict(l=10, r=10, t=30, b=10), showlegend=False,
        plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor=GRID, title="£ per member", zeroline=False),
        yaxis=dict(visible=False, range=[-1, 1]),
        font=dict(color="#1C2B3A"),
    )
    st.plotly_chart(fig2, width="stretch")

st.subheader(f"Membership composition, {fund_name}")
st.caption("Contributing members, pensioners and deferred members")
fig3 = go.Figure()
for col, label, color in [
    ("total_contributing_members", "Contributing", ACCENT),
    ("total_pensioners", "Pensioners", ACCENT2),
    ("total_deferred_members", "Deferred", GOOD),
]:
    fig3.add_trace(go.Bar(x=hist["year"], y=hist[col], name=label, marker_color=color))
fig3.update_layout(
    barmode="stack", height=260, margin=dict(l=0, r=0, t=10, b=0),
    plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(showgrid=False), yaxis=dict(gridcolor=GRID),
    legend=dict(orientation="h", yanchor="bottom", y=-0.3, x=0),
    font=dict(color="#1C2B3A"),
)
st.plotly_chart(fig3, width="stretch")

st.subheader(f"Funds ranked closest to {fund_name} by cost per member, {latest_year}")
pos = cpm.index[cpm.ecode == ecode][0]
window = cpm.iloc[max(0, pos - 5):pos + 6].reset_index(drop=True)
is_selected = window["ecode"] == ecode
display = pd.DataFrame({
    "Fund": window["local_authority"],
    "Members": window["total_members"].map("{:,.0f}".format),
    "Cost / member": window["cost_per_member"].map("£{:,.0f}".format),
})

styled = display.style.apply(
    lambda row: ["background-color: #F0E2C8" if is_selected.iloc[row.name] else "" for _ in row],
    axis=1,
)
st.dataframe(styled, hide_index=True, width="stretch")

st.caption("Source: gov.uk LGPS SF3 returns, 2016-17 to 2024-25")

st.write("")
st.markdown('<div class="ai-box">', unsafe_allow_html=True)
st.markdown("**Ask a question**")
st.caption("Placeholder -- answers a few example questions from the real data. The live Claude-based version isn't wired up here yet (see scripts/ask.py).")

EXAMPLES = {
    f"What was {fund_name}'s total expenditure in {latest_year}?": f"£{latest['total_expenditure']:,.0f}k",
    f"How many members did {fund_name} have in {latest_year}?": f"{latest['total_members']:,.0f}",
    f"What was {fund_name}'s fund value at the end of {latest_year}?": f"£{latest['market_value_end_of_year']:,.0f}k",
}

question = st.selectbox("Example question", list(EXAMPLES.keys()))
if st.button("Ask"):
    st.success(EXAMPLES[question])
st.markdown("</div>", unsafe_allow_html=True)

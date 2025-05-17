# app.py  —  Streamlit Valuation Dashboard
# --------------------------------------------------
# run:  streamlit run app.py
# --------------------------------------------------

import streamlit as st
import pandas as pd
import requests
import altair as alt
from datetime import datetime, time
from st_aggrid import AgGrid, GridOptionsBuilder

# --------------------------------------------------
# 0. Config & helpers
# --------------------------------------------------
SOURCE_URL = "https://djfunds-static.imedao.com/djapi/index_eva/dj"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0"
}
st.set_page_config(page_title="指数估值仪表盘", layout="wide", page_icon="📈")


@st.cache_data(show_spinner=False)
def _fetch_api_data_once(url: str = SOURCE_URL) -> pd.DataFrame:
    """Fetch raw JSON once and normalize to DataFrame with clean column names."""
    resp = requests.get(url, timeout=10, headers=HEADERS)
    resp.raise_for_status()
    items = resp.json()["data"]["items"]

    df = pd.json_normalize(items)

    # ---- 修正接口拼写：yeild → dividend_yield ----
    if "yeild" in df.columns and "dividend_yield" not in df.columns:
        df.rename(columns={"yeild": "dividend_yield"}, inplace=True)
    if "dividend_yield" not in df.columns:  # 兜底，防 KeyError
        df["dividend_yield"] = pd.NA

    # 方便表格显示
    df["PE (实际)"] = df["pe"]
    df["PB (实际)"] = df["pb"]

    return df[
        [
            "name",
            "index_code",
            "pe_percentile",
            "pb_percentile",
            "roe",
            "dividend_yield",
            "PE (实际)",
            "PB (实际)",
        ]
    ]


def _need_refresh(last_at: datetime | None) -> bool:
    now = datetime.now()
    tgt = datetime.combine(now.date(), time(20, 0))
    return last_at is None or (now >= tgt > last_at) or last_at.date() < now.date()


def fetch_api_data(url: str = SOURCE_URL) -> pd.DataFrame:
    if _need_refresh(st.session_state.get("last_fetch_at")):
        st.session_state["cached_df"] = _fetch_api_data_once(url)
        st.session_state["last_fetch_at"] = datetime.now()
    return st.session_state["cached_df"]


def classify(pe_pct: float, pb_pct: float) -> str:
    if pe_pct < 0.3 and pb_pct < 0.3:
        return "低估"
    if pe_pct > 0.7 or (pe_pct > 0.3 and pb_pct > 0.3):
        return "高估"
    return "适中"


# --------------------------------------------------
# 1. Sidebar
# --------------------------------------------------
with st.sidebar:
    st.title("📊 数据源设置")
    src = st.radio("选择数据来源", ("在线 API", "上传 CSV"))

    if src == "在线 API":
        df_raw = fetch_api_data()
    else:
        up = st.file_uploader("上传 CSV", type="csv")
        if up is None:
            st.stop()
        df_raw = pd.read_csv(up)

    # 百分位标准化 → 小数
    if {"pe_pct", "pb_pct"}.issubset(df_raw.columns):
        pass
    elif {"pe_percentile", "pb_percentile"}.issubset(df_raw.columns):
        if df_raw["pe_percentile"].max() > 1:
            df_raw["pe_pct"] = df_raw["pe_percentile"] / 100
            df_raw["pb_pct"] = df_raw["pb_percentile"] / 100
        else:
            df_raw.rename(
                columns={"pe_percentile": "pe_pct", "pb_percentile": "pb_pct"},
                inplace=True,
            )
    else:
        st.error("缺少 PE/PB 百分位列")
        st.stop()

    df_raw["估值判断"] = df_raw.apply(lambda r: classify(r.pe_pct, r.pb_pct), axis=1)
    sel_levels = st.multiselect(
        "筛选估值区间", ["低估", "适中", "高估"], default=["低估", "适中", "高估"]
    )

filtered = df_raw[df_raw["估值判断"].isin(sel_levels)].copy()

# --------------------------------------------------
# 2. KPI cards
# --------------------------------------------------
c1, c2, c3 = st.columns(3)
c1.metric("指数总数", len(df_raw))
c2.metric("筛选后", len(filtered))
c3.metric("低估 / 高估",
          f"{(df_raw['估值判断']=='低估').sum()} / {(df_raw['估值判断']=='高估').sum()}")

# --------------------------------------------------
# 3. Tabs
# --------------------------------------------------
scatter_tab, distrib_tab, table_tab, bubble_tab = st.tabs(
    ["⚡ 散点图", "📊 分布", "📋 数据表", "💨 Bubble Chart"]
)

# --- 3.1 Scatter ---
with scatter_tab:
    st.subheader("PE% vs PB%")
    scatter = (
        alt.Chart(filtered)
        .mark_circle(size=120, opacity=.85)
        .encode(
            x=alt.X("pe_pct", title="PE 百分位", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format=".0%")),
            y=alt.Y("pb_pct", title="PB 百分位", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format=".0%")),
            color=alt.Color("估值判断", scale=alt.Scale(domain=["低估", "适中", "高估"],
                                                     range=["#2ca25f", "#fdae6b", "#fb6a4a"]))
        ).interactive()
    )
    st.altair_chart(scatter, use_container_width=True)

# --- 3.2 Distribution ---
with distrib_tab:
    st.subheader("估值区间分布")

    distrib = (
        filtered["估值判断"].value_counts()
        .reindex(["低估", "适中", "高估"], fill_value=0)
        .reset_index()
        .rename(columns={"index": "估值", "估值判断": "数量"})
    )

    if distrib["数量"].sum() == 0:
        st.info("⚠️ 当前筛选条件下没有指数数据可显示。")
    else:
        bar = (
            alt.Chart(distrib)
            .mark_bar()
            .encode(
                x=alt.X("估值:N", title="估值区间"),      # 指明 Nominal 类型
                y=alt.Y("数量:Q", title="指数数量"),      # 指明 Quantitative 类型
                color=alt.Color(
                    "估值:N",
                    scale=alt.Scale(domain=["低估", "适中", "高估"],
                                    range=["#2ca25f", "#fdae6b", "#fb6a4a"]),
                ),
                tooltip=["估值:N", "数量:Q"]
            )
        )
        st.altair_chart(bar, use_container_width=True)

# --- 3.3 Data Table ---
with table_tab:
    st.subheader("明细表")
    tbl = filtered[[
        "name", "估值判断", "PE (实际)", "pe_pct",
        "PB (实际)", "pb_pct", "roe", "dividend_yield"
    ]].copy()
    tbl.rename(columns={
        "name": "指数名称", "pe_pct": "PE%", "pb_pct": "PB%", "dividend_yield": "股息率"}, inplace=True)
    gb = GridOptionsBuilder.from_dataframe(tbl)
    for col in ["PE%", "PB%", "roe", "股息率"]:
        gb.configure_column(col, type=["numericColumn"],
                            valueFormatter="(x*100).toFixed(2)+'%'", width=100)
    AgGrid(tbl, gridOptions=gb.build(), fit_columns_on_grid_load=True, height=420)

# --- 3.4 Bubble Chart ---
with bubble_tab:
    st.subheader("Bubble Chart (气泡大小 = 股息率)")
    bubble = (
        alt.Chart(filtered)
        .mark_circle(opacity=.6)
        .encode(
            x=alt.X("pe_pct", title="PE 百分位", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format=".0%")),
            y=alt.Y("pb_pct", title="PB 百分位", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format=".0%")),
            size=alt.Size("dividend_yield", scale=alt.Scale(range=[50, 400]), legend=None),
            color=alt.Color("估值判断", scale=alt.Scale(domain=["低估", "适中", "高估"],
                                                     range=["#2ca25f", "#fdae6b", "#fb6a4a"])),
            tooltip=["name", alt.Tooltip("pe_pct", format=".1%", title="PE%"),
                     alt.Tooltip("pb_pct", format=".1%", title="PB%"),
                     alt.Tooltip("dividend_yield", format=".2%", title="股息率"), "估值判断"]
        ).interactive()
    )
    st.altair_chart(bubble, use_container_width=True)

# --------------------------------------------------
# 4. Footer
# --------------------------------------------------
st.caption(
    "🔻 PE百分位<30%，且PB百分位<30%；\n\n"
    "🔺 PE百分位>70%，或PE百分位>30%且PB百分位>30%；\n\n"
    "⚠️ 指数数据时间较短(不满5年)，不参与估值。\n\n"
    "常用估值指标说明\n"
    "① PE指市盈率（TTM），PE（TTM）=∑成分股市值/∑成分股净利润（TTM）。数值越低，一般认为估值越低；\n"
    "② PB指市净率（MRQ），数值越低，一般认为估值越低；\n"
    "③ PE百分位代表当前PE在选定区间所处的水平，假设PE百分位为10%，表示只有10%的时候比当前市盈率低，百分位基于指数近10年PE数据计算，若不满10年则采用全部历史数据，PB百分位同理。"
)

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

# --- sidebar toggle state ---
if "sidebar_open" not in st.session_state:
    st.session_state.sidebar_open = False

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
    print("API data is updated.")

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
# 1. Sidebar toggle + filter
# --------------------------------------------------

# ---------- state init ----------
if "sidebar_open" not in st.session_state:
    st.session_state.sidebar_open = False          # default collapsed
if "sel_levels" not in st.session_state:
    st.session_state.sel_levels = ["低估", "适中", "高估"]

# ---------- toggle button ----------
label = "📂 显示筛选" if not st.session_state.sidebar_open else "❌ 隐藏筛选"
# fixed key keeps the button “clickable” even when text changes
if st.button(label, key="toggle_btn"):
    st.session_state.sidebar_open = not st.session_state.sidebar_open

# ---------- always fetch / preprocess ----------
df_raw = fetch_api_data()

# percentile → decimal
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

# add valuation label
df_raw["估值判断"] = df_raw.apply(lambda r: classify(r.pe_pct, r.pb_pct), axis=1)

# ---------- sidebar controls (only when open) ----------
if st.session_state.sidebar_open:
    with st.sidebar:
        st.title("筛选")
        st.session_state.sel_levels = st.multiselect(
            "选择估值区间",
            ["低估", "适中", "高估"],
            default=st.session_state.sel_levels,
        )

# ---------- final filtered dataframe ----------
sel_levels = st.session_state.sel_levels
filtered = df_raw[df_raw["估值判断"].isin(sel_levels)].copy()


# --------------------------------------------------
# 2. KPI cards
# --------------------------------------------------
c1, c2, c3 = st.columns(3)
c1.metric("指数总数", len(df_raw))
c2.metric("筛选后", len(filtered))
c3.metric("低估 / 高估",
          f"{(df_raw['估值判断'] == '低估').sum()} / {(df_raw['估值判断'] == '高估').sum()}")

# --------------------------------------------------
# 3. Tabs
# --------------------------------------------------
table_tab, bubble_tab, bubble_tab2 = st.tabs(
    ["📋 数据表", "💨 Bubble Chart", "💨 Bubble Chart (PE/PB)"]
)

# --- 3.1 Data Table ---
with table_tab:
    st.subheader("明细表")
    # 显示 API 抓取日期
    fetch_date = st.session_state.get("last_fetch_at")
    if fetch_date:
        st.caption(f"数据日期：{fetch_date.strftime('%Y-%m-%d')}")
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

# --- 3.2 Bubble Chart (气泡 + 右侧标签) ---
with bubble_tab:
    st.subheader("Bubble Chart (气泡大小 = 股息率)")

    chart_df = (
        filtered.dropna(subset=["pe_pct", "pb_pct", "dividend_yield"])
        .astype({"pe_pct": "float64", "pb_pct": "float64", "dividend_yield": "float64"})
    )

    if chart_df.empty:
        st.info("⚠️ 当前筛选条件下没有可绘制的数据。")
    else:
        base = alt.Chart(chart_df).encode(
            x=alt.X("pe_pct:Q", title="PE 百分位", scale=alt.Scale(domain=[0, 1]),
                    axis=alt.Axis(format=".0%")),
            y=alt.Y("pb_pct:Q", title="PB 百分位", scale=alt.Scale(domain=[0, 1]),
                    axis=alt.Axis(format=".0%")),
            color=alt.Color("估值判断:N",
                            scale=alt.Scale(domain=["低估", "适中", "高估"],
                                            range=["#2ca25f", "#fdae6b", "#fb6a4a"]))
        )

        bubbles = base.mark_circle(opacity=.6).encode(
            size=alt.Size("dividend_yield:Q", scale=alt.Scale(range=[50, 400]), legend=None),
            tooltip=[
                "name:N",
                alt.Tooltip("PE (实际):Q", title="PE"),
                alt.Tooltip("PB (实际):Q", title="PB"),
                alt.Tooltip("dividend_yield:Q", format=".2%", title="股息率"),
                "估值判断:N"
            ]
        )

        # 文字右移 8 像素，基线居中
        labels = base.mark_text(
            align="left",
            baseline="middle",
            dx=8,
            fontSize=8,
            fontWeight="bold"
        ).encode(
            text="name:N"
        )

        st.altair_chart(alt.layer(bubbles, labels).interactive(),
                        use_container_width=True)

# --- 3.3 Bubble Chart (PE / PB 实际值，气泡 + 右侧常显标签) ---
with bubble_tab2:
    st.subheader("Bubble Chart (PE / PB 实际值，气泡大小 = 股息率)")

    chart_df = (
        filtered.dropna(subset=["PE (实际)", "PB (实际)", "dividend_yield"])
        .astype({"PE (实际)": "float64", "PB (实际)": "float64", "dividend_yield": "float64"})
    )

    if chart_df.empty:
        st.info("⚠️ 当前筛选条件下没有可绘制的数据。")
    else:
        base = alt.Chart(chart_df).encode(
            x=alt.X("PE (实际):Q", title="PE (实际)", scale=alt.Scale(zero=False)),
            y=alt.Y("PB (实际):Q", title="PB (实际)", scale=alt.Scale(zero=False)),
            color=alt.Color("估值判断:N",
                            scale=alt.Scale(domain=["低估", "适中", "高估"],
                                            range=["#2ca25f", "#fdae6b", "#fb6a4a"]))
        )

        bubbles = base.mark_circle(opacity=.6).encode(
            size=alt.Size("dividend_yield:Q", scale=alt.Scale(range=[50, 400]), legend=None),
            tooltip=[
                "name:N",
                alt.Tooltip("PE (实际):Q", title="PE"),
                alt.Tooltip("PB (实际):Q", title="PB"),
                alt.Tooltip("dividend_yield:Q", format=".2%", title="股息率"),
                "估值判断:N"
            ]
        )

        # label layer: dx=8 px moves text to the right of its bubble
        labels = base.mark_text(
            align="left",
            baseline="middle",
            dx=8,  # pixel offset to avoid overlap
            fontSize=8,
            fontWeight="bold"
        ).encode(
            text="name:N"
        )

        st.altair_chart(alt.layer(bubbles, labels).interactive(),
                        use_container_width=True)

# --------------------------------------------------
# 4. Footer
# --------------------------------------------------
st.caption(
    "🔻 PE百分位<30%，且PB百分位<30%；\n\n"
    "🔺 PE百分位>70%，或PE百分位>30%且PB百分位>30%；\n\n"
    "⚠️ 指数数据时间较短(不满5年)，不参与估值。\n\n"
    "常用估值指标说明\n\n"
    "① PE指市盈率（TTM），PE（TTM）=∑成分股市值/∑成分股净利润（TTM）。数值越低，一般认为估值越低；\n"
    "② PB指市净率（MRQ），数值越低，一般认为估值越低；\n"
    "③ PE百分位代表当前PE在选定区间所处的水平，假设PE百分位为10%，表示只有10%的时候比当前市盈率低，百分位基于指数近10年PE数据计算，若不满10年则采用全部历史数据，PB百分位同理。\n\n"
    "💡 **视图小技巧** \n\n"
    "• 点击任意图表右上角 `⋮` 选择 **View fullscreen** 可放大全屏，再按 `Esc` 或点击右上角 × 退出。\n\n"
    "• Altair 图可鼠标拖拽框选缩放，双击空白处重置视图 \n"
)

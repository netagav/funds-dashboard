"""
דשבורד קרנות - Streamlit.
"""

import io
import os
import glob
import math
import contextlib
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data_source import load_data
from processing import (
    add_helper_columns, kpis, agg_by, validate,
    ASSET_LABEL,
)
from month_diff import available_months, month_diff, cross_check_with_maya
from maya_check import load_maya_file, reconcile

MAYA_DIR = Path(__file__).resolve().parent / "data" / "maya"
FUNDS_DATA_DIR = Path(__file__).resolve().parent / "data"

st.set_page_config(page_title="דשבורד קרנות", layout="wide")

# --- הגדרת תצוגה מימין לשמאל (RTL) ועיצוב מתקדם ---
st.markdown(
    """
    <style>
        /* צמצום הרווח העליון הריק של הדף כולו */
        .block-container {
            padding-top: 2rem !important;
        }
        
        /* הפיכת כיוון האפליקציה כולה */
        .stApp {
            direction: rtl;
        }
        
        /* יישור הטקסטים לימין */
        p, div, h1, h2, h3, h4, h5, h6, label, span {
            text-align: right !important;
        }
        
        /* סידור עמודות ה-KPIs שיופיעו מימין לשמאל */
        [data-testid="column"] {
            direction: rtl;
        }
        
        /* עיצוב כרטיסיות ה-KPIs */
        [data-testid="stMetric"] {
            background-color: #1E1E2E; 
            border: 1px solid #2A2A35; 
            padding: 10px 5px !important; 
            border-radius: 10px; 
            box-shadow: 0 4px 6px rgba(0,0,0,0.2); 
        }
        
        [data-testid="stMetricValue"] > div {
            color: #4DA6FF !important; 
            font-size: 1.6rem !important; 
        }
        
        [data-testid="stMetricLabel"] * {
            font-size: 0.9rem !important;
            white-space: normal !important; 
            overflow: visible !important;
        }

        /* צמצום הרווחים של קווי ההפרדה בין הטבלאות */
        hr {
            margin-top: 15px !important;
            margin-bottom: 10px !important;
        }
        
        /* עיצוב כותרות המשנה של הטבלאות (צמצום משמעותי של הרווחים) */
        h3 {
            color: #E0E0E0 !important;
            border-bottom: 2px solid #4DA6FF; 
            padding-bottom: 10px;
            margin-top: 5px !important;
            margin-bottom: 10px !important;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# --------------------------- עוזרי גרפים (Plotly, עיצוב כהה תואם) ---------------------------
CHART_BG = "#1E1E2E"
CHART_GRID = "#2A2A35"
CHART_TEXT = "#E0E0E0"
CHART_ACCENT = "#4DA6FF"     # כחול - מבטא ראשי, שמור לקו "סה"כ" בגרפי המגמה
# פלטת זהות למנהלים/סוגי קרן שנבחרו בגרפי המגמה - סדר קבוע, בלי כחול (שמור ל"סה"כ")
ENTITY_PALETTE = [
    "#81C784", "#FFB347", "#B39DDB", "#F48FB1", "#FF8A65",
    "#4DD0E1", "#FFE082", "#CE93D8", "#90A4AE", "#A1887F",
]


def _entity_colors(entities) -> dict:
    return {str(e): ENTITY_PALETTE[i % len(ENTITY_PALETTE)] for i, e in enumerate(entities)}


def _dark_layout(fig: go.Figure, height: int = 320, legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height,
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        font=dict(family="Arial, Segoe UI, sans-serif", color=CHART_TEXT, size=13),
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                     bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor=CHART_GRID, font_color=CHART_TEXT),
    )
    fig.update_xaxes(showgrid=False, color=CHART_TEXT, linecolor=CHART_GRID)
    fig.update_yaxes(showgrid=True, gridcolor=CHART_GRID, gridwidth=1, zeroline=False, color=CHART_TEXT)
    return fig


def _trend_chart(x, series: dict, colors: dict, y_title: str = "", pct: bool = False) -> go.Figure:
    """גרף קו למגמה היסטורית. 'סה"כ' תמיד בכחול המבטא, עבה ומקווקו כדי
    לבלוט; שאר הסדרות (מנהלים/סוגי קרן שנבחרו) בפלטת הזהות הקבועה."""
    fig = go.Figure()
    suffix = "%" if pct else ""
    for name, y in series.items():
        is_total = name == 'סה"כ'
        fig.add_trace(go.Scatter(
            x=x, y=y, mode="lines+markers", name=name,
            line=dict(
                width=3 if is_total else 2,
                color=CHART_ACCENT if is_total else colors.get(name, CHART_ACCENT),
                dash="dash" if is_total else "solid",
            ),
            marker=dict(size=6 if is_total else 5),
            connectgaps=False,
            hovertemplate=f"%{{x|%Y-%m}}<br>{name}: %{{y:,.2f}}{suffix}<extra></extra>",
        ))
    fig.update_xaxes(tickformat="%Y-%m")
    fig.update_yaxes(title_text=y_title)
    return _dark_layout(fig, legend=True)


def _data_signature() -> tuple:
    files = sorted(glob.glob(str(FUNDS_DATA_DIR / "funds_*.csv")))
    return tuple((f, os.path.getmtime(f)) for f in files)

@st.cache_data
def get_data(signature: tuple) -> pd.DataFrame:
    df = load_data()
    return add_helper_columns(df)

@st.cache_data(show_spinner=False)
def get_maya(latest_month: str):
    """קורא את snapshot המאיה של החודש מהגיט (קפוא). אם אין קובץ לחודש הזה —
    מחזיר None (הורדה חיה נעשית רק ב-refresh_maya, לא כאן)."""
    path = MAYA_DIR / f"maya_{latest_month}.csv"
    if path.exists():
        return load_maya_file(path)
    return None

df = get_data(_data_signature())
df["year"] = pd.to_datetime(df["eom"]).dt.year

# --------------------------- סיידבר: ניווט, חודש ואימות ---------------------------

# 1. תפריט ניווט מהיר מעוצב וקומפקטי (TOC)
st.sidebar.markdown(
    """
    <style>
        .toc-container {
            margin-top: -40px; /* צמצום הרווח העליון המוגזם של הסיידבר */
        }
        .toc-container a {
            text-decoration: none !important;
            border-bottom: none !important;
            box-shadow: none !important;
            display: block;
            margin-bottom: 6px; /* הקטנת הרווח בין הקישורים */
            font-weight: 500;
            font-size: 14px !important;
            transition: opacity 0.2s;
        }
        .toc-container a:hover {
            opacity: 0.7;
        }
    </style>
    <div class="toc-container" style="text-align: right; direction: rtl;">
        <div style="color: #A3A8B8; font-size: 15px; font-weight: bold; margin-bottom: 5px;">
            ניווט מהיר 📄
        </div>
        <hr style="border: 0; border-top: 1px solid #333852; margin-top: 5px; margin-bottom: 10px;">
        <a href="#-דשבורד-קרנות"><span style="color: #FFB347;">מדדים מרכזיים (KPIs) 📊</span></a>
        <a href="#-לפי-מנהל-קרן"><span style="color: #B39DDB;">לפי מנהל קרן 👥</span></a>
        <a href="#-מחקהסל-לפי-סוג-נכס"><span style="color: #F48FB1;">מחקה/סל לפי סוג נכס 🎯</span></a>
        <hr style="border: 0; border-top: 1px solid #333852; margin-top: 10px; margin-bottom: 15px;">
    </div>
    """,
    unsafe_allow_html=True
)

# 2. מסנן תקופה: שנה ואז חודש (אוחד ללא כותרת כדי לחסוך מקום)
months = sorted(df["eom"].unique())

if not months:
    st.warning("לא נמצאו נתונים. אנא ודא שקובץ ה-CSV קיים בתיקיית data.")
    st.stop()

years = sorted(df["year"].unique())


def _last_month_of_year(y):
    yr_months = sorted(df.loc[df["year"] == y, "eom"].unique())
    return yr_months[-1]


def _on_year_change():
    st.session_state["month_select"] = _last_month_of_year(st.session_state["year_select"])


year = st.sidebar.selectbox(
    "📅 שנה", years, index=len(years) - 1, key="year_select", on_change=_on_year_change
)

month_options = sorted(df.loc[df["year"] == year, "eom"].unique())

if "month_select" not in st.session_state or st.session_state["month_select"] not in month_options:
    st.session_state["month_select"] = month_options[-1]

month = st.sidebar.selectbox("🗓️ חודש", month_options, key="month_select")

base = df[df["eom"] == month]

# --------------------------- KPIs ---------------------------
st.title("📊 דשבורד קרנות")
st.caption(f"📅 חודש: {month}")

k = kpis(base)
cols = st.columns(6)
cols[0].metric("💰 סך נכסים (₪M)", f"{k['aum_m']:,.0f}")
cols[1].metric("📈 הכנסות ברוטו (₪M)", f"{k['rev_gross_m']:,.0f}")
cols[2].metric("💎 הכנסות נטו (₪M)", f"{k['rev_net_m']:,.0f}")
cols[3].metric("🏢 מס' קרנות", f"{k['n_funds']:,}")
cols[4].metric("⚖️ דמי ניהול ברוטו", f"{k['fee_gross_pct']:.2f}%")
cols[5].metric("🛡️ דמי ניהול נטו", f"{k['fee_net_pct']:.2f}%")

st.markdown("<br>", unsafe_allow_html=True)
st.divider()

# --------------------------- עוזר תצוגה ---------------------------
def render(g, label_col, label_name, market_share=False, highlight_row=None, market_share_bar=True):
    g_copy = g.copy()
    g_copy = g_copy.sort_values("aum_m", ascending=False)  # = מיון לפי נתח שוק יורד (יחס קבוע ל-aum_m)

    # מקסימום נתח השוק בין השורות בפועל (בלי שורת הסה"כ) - לקנה המידה של הבר
    if market_share:
        individual_max_share = float(g_copy["market_share_pct"].max())

    total_aum_raw = g_copy["aum"].sum()
    total_rev_raw = g_copy["rev"].sum()
    total_nrev_raw = g_copy["nrev"].sum()

    total_fee_gross = (total_rev_raw / total_aum_raw * 10000) if total_aum_raw else 0.0
    total_fee_net = (total_nrev_raw / total_aum_raw * 10000) if total_aum_raw else 0.0

    total_row = {
        label_col: 'סה"כ',
        "aum_m": g_copy["aum_m"].sum(),
        "fee_gross_pct": total_fee_gross,
        "fee_net_pct": total_fee_net,
    }

    if market_share:
        total_row["market_share_pct"] = g_copy["market_share_pct"].sum()

    g_copy = pd.concat([g_copy, pd.DataFrame([total_row])], ignore_index=True)

    out = pd.DataFrame({
        label_name: g_copy[label_col],
        "נכסים (₪M)": g_copy["aum_m"],
        "דמי ניהול ברוטו %": g_copy["fee_gross_pct"],
        "דמי ניהול נטו %": g_copy["fee_net_pct"],
    })

    if market_share:
        out["נתח שוק %"] = g_copy["market_share_pct"]

    out = out[out.columns[::-1]]

    format_dict = {
        "נכסים (₪M)": "{:,.0f}",
        "דמי ניהול ברוטו %": "{:,.2f}",
        "דמי ניהול נטו %": "{:,.2f}",
    }

    column_config = None
    if market_share and market_share_bar:
        # max_value לפי המקסימום בפועל בין השורות (בלי שורת הסה"כ), מעוגל כלפי
        # מעלה לכפולת-5 נוחה - כך שהבר של המנהל הגדול ביותר ימלא כמעט את כל
        # התא וההבדלים בין המנהלים נראים ברור, במקום שכולם יידחסו מול 100%.
        # שורת הסה"כ (100%) חורגת מה-max_value בכוונה: הטקסט המספרי שלה
        # ("100.00%") עדיין מוצג נכון, והבר שלה פשוט מוצג מלא (clamped).
        max_share = math.ceil(individual_max_share / 5) * 5
        column_config = {
            "נתח שוק %": st.column_config.ProgressColumn(
                "נתח שוק %", format="%.2f%%", min_value=0, max_value=max_share,
            ),
        }
    elif market_share:
        format_dict["נתח שוק %"] = "{:,.2f}"

    def highlight_total(row):
        if row[label_name] == 'סה"כ':
            return ['background-color: #2A2A35; font-weight: bold; color: #4DA6FF'] * len(row)
        if highlight_row is not None and row[label_name] == highlight_row:
            return ['color: #FFA500; font-weight: bold'] * len(row)
        return [''] * len(row)

    st.dataframe(
        out.style.format(format_dict).apply(highlight_total, axis=1),
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=(len(out) + 1) * 35
    )

def render_diff(frame: pd.DataFrame):
    fixed_cols = [c for c in ["FundBno", "ShortName", "ManagerCmp", "SuperClass", "fdAUM"] if c in frame.columns]
    extra_cols = [c for c in frame.columns if c not in fixed_cols]

    out = frame[fixed_cols + extra_cols].copy()
    if "FundBno" in out.columns:
        out["FundBno"] = out["FundBno"].apply(lambda v: str(int(v)) if pd.notna(v) else "")
    if "fdAUM" in out.columns:
        out["fdAUM"] = out["fdAUM"] / 1_000_000
        out = out.rename(columns={"fdAUM": "נכסים (₪M)"})
    out = out[out.columns[::-1]]

    total_row = {c: "" for c in out.columns}
    if "FundBno" in out.columns:
        total_row["FundBno"] = 'סה"כ'
    if "נכסים (₪M)" in out.columns:
        total_row["נכסים (₪M)"] = out["נכסים (₪M)"].sum(skipna=True)
    out = pd.concat([out, pd.DataFrame([total_row])], ignore_index=True)

    def highlight_total(row):
        if "FundBno" in row.index and row["FundBno"] == 'סה"כ':
            return ['background-color: #2A2A35; font-weight: bold; color: #4DA6FF'] * len(row)
        return [''] * len(row)

    st.dataframe(
        out.style.format({"נכסים (₪M)": "{:,.0f}"}).apply(highlight_total, axis=1),
        use_container_width=True,
        hide_index=True,
        height=(len(frame) + 2) * 35
    )

# --------------------------- טבלה 1 - לפי מנהל ---------------------------
st.subheader("👥 לפי מנהל קרן")

# יצירת רשימה דינמית של קטגוריות העל מתוך הנתונים (הפעם ללא המילה "הכל")
super_classes = sorted(base["SuperClass"].dropna().unique().tolist())
fund_types = ["מחקה", "סל", "כספית", "אקטיבית"]

# סידור המסננים בשורה אחת
col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 2, 3])

with col_f1:
    # שימוש ב-multiselect. placeholder מציג טקסט כשהשדה ריק
    mgr_type_opt = st.multiselect("סינון סוג קרן", fund_types, placeholder="הכל (בחר כדי לסנן)", key="mgr_type")
with col_f2:
    # את ההוסטינג נשאיר כרגע כ-selectbox כי יש רק מעט אופציות
    mgr_host_opt = st.selectbox("סינון הוסטינג", ["הכל", "ללא הוסטינג", "הוסטינג"], key="mgr_host")
with col_f3:
    # שימוש ב-multiselect גם לקטגוריית על
    mgr_super_opt = st.multiselect("סינון קטגוריית על", super_classes, placeholder="הכל (בחר כדי לסנן)", key="mgr_super")

# הכנת הנתונים
scope_mgr = base.copy()
scope_mgr["ManagerCmp"] = scope_mgr["ManagerCmp"].fillna("לא ידוע/טרם סווג")

# החלת מסננים - שים לב לשינוי בלוגיקה
if mgr_type_opt:  # אם הרשימה לא ריקה (כלומר המשתמש בחר לפחות אופציה אחת)
    scope_mgr = scope_mgr[scope_mgr["FundType"].isin(mgr_type_opt)]
    
if mgr_host_opt != "הכל":
    scope_mgr = scope_mgr[scope_mgr["IsHosting"] == mgr_host_opt]
    
if mgr_super_opt: # אם הרשימה לא ריקה
    scope_mgr = scope_mgr[scope_mgr["SuperClass"].isin(mgr_super_opt)]

# יצירת הטבלה והצגתה
m = agg_by(scope_mgr, "ManagerCmp").sort_values("aum_m", ascending=False)
render(m, "ManagerCmp", "מנהל", market_share=True, highlight_row="מגדל")

st.divider()

# --------------------------- טבלה 4 - מחקה/סל לפי סוג נכס ---------------------------
st.subheader("🎯 מחקה/סל לפי סוג נכס")

# הוסר מסנן ההוסטינג לחלוטין - מציג תמיד את התמונה המלאה
tr = base[base["FundType"].isin(["מחקה", "סל"])].copy()
tr["grp"] = tr["FundType"] + " " + tr["AssetClass"].map(ASSET_LABEL)
a = agg_by(tr, "grp").sort_values("aum_m", ascending=False)
render(a, "grp", "קטגוריה", market_share=True, market_share_bar=False)

st.divider()

# --------------------------- מגמה היסטורית ---------------------------
st.subheader("📈 מגמה היסטורית", anchor="trend")

col_t1, col_t2, col_t3 = st.columns([2, 2, 3])
with col_t1:
    trend_type_opt = st.multiselect(
        "סינון סוג קרן", fund_types, placeholder="הכל (בחר כדי לסנן)", key="trend_type"
    )
with col_t2:
    trend_host_opt = st.selectbox(
        "סינון הוסטינג", ["הכל", "ללא הוסטינג", "הוסטינג"], key="trend_host"
    )
with col_t3:
    managers_all = sorted(df["ManagerCmp"].dropna().unique().tolist())
    trend_mgr_opt = st.multiselect(
        "סינון מנהל קרן", managers_all, placeholder="הכל (בחר כדי לסנן)", key="trend_mgr"
    )

scope_trend = df.copy()
if trend_type_opt:
    scope_trend = scope_trend[scope_trend["FundType"].isin(trend_type_opt)]
if trend_host_opt != "הכל":
    scope_trend = scope_trend[scope_trend["IsHosting"] == trend_host_opt]
if trend_mgr_opt:
    scope_trend = scope_trend[scope_trend["ManagerCmp"].isin(trend_mgr_opt)]

# בחירת מסנן הפיצול לקווים: אם גם סוג קרן וגם מנהל נבחרו יחד, מפצלים
# לפי זה שבו נבחרו יותר פריטים (כדי לא ליצור מכפלה של כל הצירופים);
# בשוויון מעדיפים מנהל קרן. הוסטינג תמיד נשאר פילטר רגיל, לא מפצל.
if trend_mgr_opt and trend_type_opt:
    if len(trend_mgr_opt) >= len(trend_type_opt):
        split_col, split_entities = "ManagerCmp", trend_mgr_opt
    else:
        split_col, split_entities = "FundType", trend_type_opt
elif trend_mgr_opt:
    split_col, split_entities = "ManagerCmp", trend_mgr_opt
elif trend_type_opt:
    split_col, split_entities = "FundType", trend_type_opt
else:
    split_col, split_entities = None, []

entity_colors = _entity_colors(split_entities)
all_eoms = sorted(scope_trend["eom"].unique())
x = pd.to_datetime(all_eoms)

# agg_by לפי eom פעם אחת לכל ישות (כולל "סה"כ") - משמש לכל שלושת
# גרפי המגמה יחד, כדי לא לחשב אגרגציה בנפרד לכל גרף
hist_frames = {'סה"כ': agg_by(scope_trend, "eom").set_index("eom").reindex(all_eoms)}
for ent in split_entities:
    sub = scope_trend[scope_trend[split_col] == ent]
    if sub.empty:
        hist_frames[str(ent)] = pd.DataFrame(
            index=all_eoms, columns=["aum_m", "fee_gross_pct", "fee_net_pct"], dtype="float64"
        )
    else:
        hist_frames[str(ent)] = agg_by(sub, "eom").set_index("eom").reindex(all_eoms)


def _series_for(col: str) -> dict:
    return {name: frame[col] for name, frame in hist_frames.items()}


st.markdown("**נכסים כוללים (₪M)**")
st.plotly_chart(
    _trend_chart(x, _series_for("aum_m"), entity_colors, y_title="₪M"),
    use_container_width=True,
)

st.markdown("**דמי ניהול ברוטו %**")
st.plotly_chart(
    _trend_chart(x, _series_for("fee_gross_pct"), entity_colors, y_title="%", pct=True),
    use_container_width=True,
)

st.markdown("**דמי ניהול נטו %**")
st.plotly_chart(
    _trend_chart(x, _series_for("fee_net_pct"), entity_colors, y_title="%", pct=True),
    use_container_width=True,
)

st.divider()

# --------------------------- שינוי לעומת החודש הקודם ---------------------------
st.markdown(
    """
    <style>
        /* קלף "שינוי לעומת החודש הקודם" - בולט משאר הדשבורד, לא סתם expander גנרי */
        .st-key-changes-card,
        .st-key-changes-card [data-testid="stExpander"] {
            background-color: rgba(255, 138, 101, 0.06);
            border: 1px solid #FF8A65;
            border-right: 4px solid #FF8A65;
            border-radius: 10px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.expander("🔄 שינוי לעומת החודש הקודם", expanded=False, key="changes-card"):
    mts = available_months(df)
    if len(mts) < 2:
        st.info("צריך לפחות שני חודשים בנתונים כדי להשוות. הסעיף יופיע אוטומטית כשייכנס החודש הבא.")
    else:
        diff_idx = mts.index(month)

        if diff_idx == 0:
            st.info("אין חודש קודם להשוואה")
        else:
            m_prev = mts[diff_idx - 1]
            st.caption(
                f"ההשוואה היא מול החודש הקודם "
                f"(<span style='direction: ltr; unicode-bidi: embed;'>{m_prev}</span>)",
                unsafe_allow_html=True,
            )

            use_maya = st.checkbox("הצלב מול המאיה", key="diff_maya")

            d = month_diff(df, m_prev, month)

            if use_maya:
                maya_df = get_maya(month)
                if maya_df is None:
                    st.info("אין snapshot של המאיה לחודש זה")
                else:
                    d = cross_check_with_maya(d, maya_df)

            k1, k2 = st.columns(2)
            k1.metric("יצאו (פורקו/נסגרו)", f"{d['counts']['exited']:,}")
            k2.metric("נכנסו (חדשות)", f"{d['counts']['entered']:,}")

            st.markdown("**קרנות שיצאו** (היו בחודש הבסיס, אינן בחודש ההשוואה):")
            render_diff(d["exited"])

            st.markdown("**קרנות שנכנסו** (בחודש ההשוואה, לא היו בבסיס):")
            render_diff(d["entered"])

# --------------------------- ייצוא נתונים ואימות (בסיידבר) ---------------------------
csv_data = base.to_csv(index=False).encode('utf-8-sig')

st.sidebar.download_button(
    label="📥 הורד נתוני חודש נוכחי",
    data=csv_data,
    file_name=f"funds_data_{month}.csv",
    mime="text/csv",
    use_container_width=True
)

with st.sidebar.expander("🔍 אימות נתונים מול המאיה"):
    st.markdown("**מול המאיה**")
    maya_df = get_maya(month)
    if maya_df is None:
        st.info("אין snapshot של המאיה לחודש זה")
    else:
        maya_result = reconcile(base, maya_df)
        n_maya_not_sql = maya_result["counts"]["maya_not_sql"]
        n_sql_not_maya = maya_result["counts"]["sql_not_maya"]
        if n_maya_not_sql == 0 and n_sql_not_maya == 0:
            st.success("לא קיים פער — כל הקרנות תואמות למאיה")
        else:
            st.caption(f"במאיה ולא בקובץ נתונים: {n_maya_not_sql}")
            if n_maya_not_sql:
                st.caption(", ".join(str(x) for x in maya_result["maya_not_sql"]["FundNumber"]))
            st.caption(f"בקובץ נתונים ולא במאיה: {n_sql_not_maya}")
            if n_sql_not_maya:
                st.caption(", ".join(str(x) for x in maya_result["sql_not_maya"]["FundNumber"]))

    st.markdown("---")

    if len(months) < 2:
        st.info("צריך שני חודשים כדי להשוות")
    else:
        idx = months.index(month)
        if idx == 0:
            st.markdown("**מול החודש הקודם**")
            st.info("אין חודש קודם לחודש הנבחר להשוואה")
        else:
            m_prev = months[idx - 1]
            st.markdown(f"**מול החודש הקודם ({m_prev} ← {month})**")
            d_prev = month_diff(df, m_prev, month)
            n_entered = d_prev["counts"]["entered"]
            n_exited = d_prev["counts"]["exited"]
            if n_entered == 0 and n_exited == 0:
                st.info("אין שינוי בין החודשים")
            else:
                st.caption(f"נכנסו: {n_entered}")
                if n_entered:
                    st.caption(", ".join(str(x) for x in d_prev["entered"]["FundBno"]))
                st.caption(f"יצאו: {n_exited}")
                if n_exited:
                    st.caption(", ".join(str(x) for x in d_prev["exited"]["FundBno"]))
"""
דשבורד קרנות - Streamlit.
"""

import io
import os
import glob
import contextlib
from pathlib import Path

import pandas as pd
import streamlit as st

from data_source import load_data
from processing import (
    add_helper_columns, kpis, agg_by, validate,
    FUND_TYPES, ASSET_LABEL,
)
from month_diff import available_months, month_diff, cross_check_with_maya
from maya_check import download_maya, load_maya_file, reconcile

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

def _data_signature() -> tuple:
    files = sorted(glob.glob(str(FUNDS_DATA_DIR / "funds_*.csv")))
    return tuple((f, os.path.getmtime(f)) for f in files)

@st.cache_data
def get_data(signature: tuple) -> pd.DataFrame:
    df = load_data()
    return add_helper_columns(df)

@st.cache_data(show_spinner=False)
def get_maya(latest_month: str) -> pd.DataFrame:
    """קורא את snapshot המאיה של החודש מהגיט (קפוא). אם אין קובץ לחודש הזה —
    מוריד חי פעם אחת (fallback לא-קפוא, עד שירוץ refresh_maya וייעשה commit)."""
    path = MAYA_DIR / f"maya_{latest_month}.csv"
    if path.exists():
        return load_maya_file(path)
    return download_maya(save_to=path)

df = get_data(_data_signature())

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
        <a href="#-לפי-סוג-קרן"><span style="color: #4DA6FF;">לפי סוג קרן 📋</span></a>
        <a href="#-לפי-הוסטינג"><span style="color: #81C784;">לפי הוסטינג 🤝</span></a>
        <a href="#-מחקהסל-לפי-סוג-נכס"><span style="color: #F48FB1;">מחקה/סל לפי סוג נכס 🎯</span></a>
        <a href="#changes"><span style="color: #FF8A65;">שינויים בין חודשים 🔄</span></a>
        <hr style="border: 0; border-top: 1px solid #333852; margin-top: 10px; margin-bottom: 15px;">
    </div>
    """,
    unsafe_allow_html=True
)

# 2. מסנן תקופה (אוחד ללא כותרת כדי לחסוך מקום)
months = sorted(df["eom"].unique())

if not months:
    st.warning("לא נמצאו נתונים. אנא ודא שקובץ ה-CSV קיים בתיקיית data.")
    st.stop()
    
month = st.sidebar.selectbox("🗓️ מסנן תקופה", months, index=len(months) - 1)

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
def render(g, label_col, label_name, market_share=False, highlight_row=None):
    g_copy = g.copy()
    
    total_aum_raw = g_copy["aum"].sum()
    total_rev_raw = g_copy["rev"].sum()
    total_nrev_raw = g_copy["nrev"].sum()
    
    total_fee_gross = (total_rev_raw / total_aum_raw * 10000) if total_aum_raw else 0.0
    total_fee_net = (total_nrev_raw / total_aum_raw * 10000) if total_aum_raw else 0.0
    
    total_row = {
        label_col: 'סה"כ',
        "aum_m": g_copy["aum_m"].sum(),
        "rev_gross_m": g_copy["rev_gross_m"].sum(),
        "rev_net_m": g_copy["rev_net_m"].sum(),
        "fee_gross_pct": total_fee_gross,
        "fee_net_pct": total_fee_net,
    }
    
    if market_share:
        total_row["market_share_pct"] = g_copy["market_share_pct"].sum()
        
    g_copy = pd.concat([g_copy, pd.DataFrame([total_row])], ignore_index=True)

    out = pd.DataFrame({
        label_name: g_copy[label_col],
        "נכסים (₪M)": g_copy["aum_m"],
        "הכנסות ברוטו (₪M)": g_copy["rev_gross_m"],
        "הכנסות נטו (₪M)": g_copy["rev_net_m"],
        "דמי ניהול ברוטו %": g_copy["fee_gross_pct"],
        "דמי ניהול נטו %": g_copy["fee_net_pct"],
    })
    
    if market_share:
        out["נתח שוק %"] = g_copy["market_share_pct"]
        
    out = out[out.columns[::-1]]
    
    format_dict = {
        "נכסים (₪M)": "{:,.0f}",
        "הכנסות ברוטו (₪M)": "{:,.2f}",
        "הכנסות נטו (₪M)": "{:,.2f}",
        "דמי ניהול ברוטו %": "{:,.2f}",
        "דמי ניהול נטו %": "{:,.2f}",
        "נתח שוק %": "{:,.2f}"
    }
    
    def highlight_total(row):
        if row[label_name] == 'סה"כ':
            return ['background-color: #2A2A35; font-weight: bold; color: #4DA6FF'] * len(row)
        if highlight_row is not None and row[label_name] == highlight_row:
            return ['color: #FFA500; font-weight: bold'] * len(row)
        return [''] * len(row)

    st.dataframe(
        out.style.format(format_dict).apply(highlight_total, axis=1),
        use_container_width=True, 
        hide_index=True,
        height=(len(out) + 1) * 35
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
render(a, "grp", "קטגוריה", market_share=True)

st.divider()

# --------------------------- שינויים בין חודשים (נכנסו / יצאו) ---------------------------
st.subheader("🔄 שינויים בין חודשים", anchor="changes")

mts = available_months(df)
if len(mts) < 2:
    st.info("צריך לפחות שני חודשים בנתונים כדי להשוות. הסעיף יופיע אוטומטית כשייכנס החודש הבא.")
else:
    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        m_old = st.selectbox("חודש בסיס", mts, index=len(mts) - 2, key="diff_old")
    with c2:
        m_new = st.selectbox("חודש להשוואה", mts, index=len(mts) - 1, key="diff_new")
    with c3:
        use_maya = st.checkbox("הצלב מול המאיה", key="diff_maya")

    d = month_diff(df, m_old, m_new)

    if use_maya:
        try:
            with st.spinner("מוריד נתונים מהמאיה..."):
                d = cross_check_with_maya(d, get_maya(mts[-1]))
        except Exception as e:
            st.warning(f"הצלבת המאיה נכשלה: {e}")

    k1, k2 = st.columns(2)
    k1.metric("יצאו (פורקו/נסגרו)", f"{d['counts']['exited']:,}")
    k2.metric("נכנסו (חדשות)", f"{d['counts']['entered']:,}")

    st.markdown("**קרנות שיצאו** (היו בחודש הבסיס, אינן בחודש ההשוואה):")
    st.dataframe(
        d["exited"], use_container_width=True, hide_index=True,
        height=(min(len(d["exited"]), 12) + 1) * 35
    )

    st.markdown("**קרנות שנכנסו** (בחודש ההשוואה, לא היו בבסיס):")
    st.dataframe(
        d["entered"], use_container_width=True, hide_index=True,
        height=(min(len(d["entered"]), 12) + 1) * 35
    )

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
    try:
        with st.spinner("מוריד נתונים מהמאיה..."):
            maya_df = get_maya(month)
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
    except Exception as e:
        st.warning(f"הצלבת המאיה נכשלה: {e}")

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
"""
דשבורד קרנות - Streamlit.
"""

import io
import contextlib

import pandas as pd
import streamlit as st

from data_source import load_data
from processing import (
    add_helper_columns, kpis, agg_by, validate,
    FUND_TYPES, ASSET_LABEL,
)

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

@st.cache_data
def get_data() -> pd.DataFrame:
    df = load_data()
    return add_helper_columns(df)

df = get_data()

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
def render(g, label_col, label_name, market_share=False):
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
        return [''] * len(row)

    st.dataframe(
        out.style.format(format_dict).apply(highlight_total, axis=1),
        use_container_width=True, 
        hide_index=True,
        height=(len(out) + 1) * 35
    )

# --------------------------- טבלה 1 - לפי מנהל ---------------------------
st.subheader("👥 לפי מנהל קרן")

# יצירת רשימה דינמית של קטגוריות העל מתוך הנתונים (ללא ערכים ריקים)
super_classes = ["הכל"] + sorted(base["SuperClass"].dropna().unique().tolist())

# סידור 3 מסננים בשורה אחת
col_f1, col_f2, col_f3, col_f4 = st.columns([2, 2, 2, 3])
with col_f1:
    mgr_type_opt = st.selectbox("סינון סוג קרן", ["הכל", "מחקה", "סל", "כספית", "אקטיבית"], key="mgr_type")
with col_f2:
    mgr_host_opt = st.selectbox("סינון הוסטינג", ["הכל", "ללא הוסטינג", "הוסטינג"], key="mgr_host")
with col_f3:
    mgr_super_opt = st.selectbox("סינון קטגוריית על", super_classes, key="mgr_super")

# החלת כל המסננים שנבחרו על נתוני הטבלה
scope_mgr = base
if mgr_type_opt != "הכל":
    scope_mgr = scope_mgr[scope_mgr["FundType"] == mgr_type_opt]
if mgr_host_opt != "הכל":
    scope_mgr = scope_mgr[scope_mgr["IsHosting"] == mgr_host_opt]
if mgr_super_opt != "הכל":
    scope_mgr = scope_mgr[scope_mgr["SuperClass"] == mgr_super_opt]

m = agg_by(scope_mgr, "ManagerCmp").sort_values("aum_m", ascending=False)
render(m, "ManagerCmp", "מנהל", market_share=True)

st.divider()

# --------------------------- טבלה 2 - לפי סוג קרן ---------------------------
st.subheader("📋 לפי סוג קרן")
col_f4, col_f5 = st.columns([2, 4])
with col_f4:
    ft_host_opt = st.selectbox("סינון הוסטינג", ["הכל", "ללא הוסטינג", "הוסטינג"], key="ft_host")

scope_ft = base if ft_host_opt == "הכל" else base[base["IsHosting"] == ft_host_opt]
ft = agg_by(scope_ft, "FundType").set_index("FundType").reindex(FUND_TYPES).reset_index()
ft = ft.sort_values("aum_m", ascending=False)
render(ft, "FundType", "סוג קרן")

st.divider()

# --------------------------- טבלה 3 - לפי הוסטינג ---------------------------
st.subheader("🤝 לפי הוסטינג")
col_f6, col_f7 = st.columns([2, 4])
with col_f6:
    host_type_opt = st.selectbox("סינון סוג קרן", ["הכל", "מחקה", "סל", "כספית", "אקטיבית"], key="host_type")

scope_host = base if host_type_opt == "הכל" else base[base["FundType"] == host_type_opt]
h = agg_by(scope_host, "IsHosting").sort_values("aum_m", ascending=False)
render(h, "IsHosting", "הוסטינג")

st.divider()

# --------------------------- טבלה 4 - מחקה/סל לפי סוג נכס ---------------------------
st.subheader("🎯 מחקה/סל לפי סוג נכס")

# הוסר מסנן ההוסטינג לחלוטין - מציג תמיד את התמונה המלאה
tr = base[base["FundType"].isin(["מחקה", "סל"])].copy()
tr["grp"] = tr["FundType"] + " " + tr["AssetClass"].map(ASSET_LABEL)
a = agg_by(tr, "grp").sort_values("aum_m", ascending=False)
render(a, "grp", "קטגוריה", market_share=True)

# --------------------------- ייצוא נתונים ואימות (בסיידבר) ---------------------------
csv_data = base.to_csv(index=False).encode('utf-8-sig')

st.sidebar.download_button(
    label="📥 הורד נתוני חודש נוכחי",
    data=csv_data,
    file_name=f"funds_data_{month}.csv",
    mime="text/csv",
    use_container_width=True
)

with st.sidebar.expander("🔍 בדיקת אימות (יוני 2026)"):
    ref_month = "2026-06-30"
    if ref_month in months:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = validate(df[df["eom"] == ref_month])
        st.code(buf.getvalue())
        st.success("הכול תואם ✓") if ok else st.error("יש סטייה — בדוק REV_TO_M")
    else:
        st.info(f"חודש הייחוס {ref_month} לא נטען עדיין.")
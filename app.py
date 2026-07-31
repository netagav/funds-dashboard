"""
דשבורד קרנות - Streamlit.

כללי תגובת המסננים (חשוב!):
  KPIs + טבלת מנהלים  -> מגיבים לכל 3 המסננים
  טבלת סוג קרן         -> מתעלמת ממסנן הסוג; מגיבה לחודש + הוסטינג
  טבלת סוג נכס         -> מתעלמת ממסנן הסוג; מגיבה לחודש + הוסטינג
  טבלת הוסטינג         -> מתעלמת ממסנן ההוסטינג; מגיבה לחודש + סוג
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


@st.cache_data
def get_data() -> pd.DataFrame:
    df = load_data()
    return add_helper_columns(df)


df = get_data()

# --------------------------- מסננים ---------------------------
st.sidebar.header("מסננים")
months = sorted(df["eom"].unique())
month = st.sidebar.selectbox("חודש", months, index=len(months) - 1)
type_opt = st.sidebar.selectbox("סוג קרן", ["הכל", "מחקה", "סל", "כספית", "אקטיבית"])
host_opt = st.sidebar.selectbox("הוסטינג", ["הכל", "ללא הוסטינג", "הוסטינג"])

base = df[df["eom"] == month]


def apply_type(d):
    return d if type_opt == "הכל" else d[d["FundType"] == type_opt]


def apply_host(d):
    return d if host_opt == "הכל" else d[d["IsHosting"] == host_opt]


scope_all = apply_host(apply_type(base))   # KPIs + מנהלים
scope_mh = apply_host(base)                # סוג קרן + סוג נכס (מתעלם מהסוג)
scope_mt = apply_type(base)                # הוסטינג (מתעלם מההוסטינג)

# --------------------------- KPIs ---------------------------
st.title("דשבורד קרנות")
st.caption(f"חודש: {month}")

k = kpis(scope_all)
cols = st.columns(6)
cols[0].metric("סך נכסים (₪M)", f"{k['aum_m']:,.0f}")
cols[1].metric("הכנסות ברוטו (₪M)", f"{k['rev_gross_m']:,.2f}")
cols[2].metric("הכנסות נטו (₪M)", f"{k['rev_net_m']:,.2f}")
cols[3].metric("מס' קרנות", f"{k['n_funds']:,}")
cols[4].metric("דמי ניהול ברוטו", f"{k['fee_gross_pct']:.2f}%")
cols[5].metric("דמי ניהול נטו", f"{k['fee_net_pct']:.2f}%")

st.divider()


# --------------------------- עוזר תצוגה ---------------------------
def render(g, label_col, label_name, market_share=False):
    out = pd.DataFrame({
        label_name: g[label_col],
        "נכסים (₪M)": g["aum_m"].round(0),
        "הכנסות ברוטו (₪M)": g["rev_gross_m"].round(2),
        "הכנסות נטו (₪M)": g["rev_net_m"].round(2),
        "דמי ניהול ברוטו %": g["fee_gross_pct"].round(2),
        "דמי ניהול נטו %": g["fee_net_pct"].round(2),
    })
    if market_share:
        out["נתח שוק %"] = g["market_share_pct"].round(2)
    st.dataframe(out, use_container_width=True, hide_index=True)


# טבלה 1 - לפי מנהל
st.subheader("לפי מנהל קרן")
m = agg_by(scope_all, "ManagerCmp").sort_values("aum_m", ascending=False)
render(m, "ManagerCmp", "מנהל", market_share=True)

# טבלה 2 - לפי סוג קרן (תמיד כל 4 הסוגים)
st.subheader("לפי סוג קרן")
ft = agg_by(scope_mh, "FundType").set_index("FundType").reindex(FUND_TYPES).reset_index()
ft = ft.sort_values("aum_m", ascending=False)
render(ft, "FundType", "סוג קרן")

# טבלה 3 - לפי הוסטינג
st.subheader("לפי הוסטינג")
h = agg_by(scope_mt, "IsHosting").sort_values("aum_m", ascending=False)
render(h, "IsHosting", "הוסטינג")

# טבלה 4 - מחקה/סל לפי סוג נכס (נתח מתוך יקום מחקה+סל = 100%)
st.subheader('מחקה/סל לפי סוג נכס')
tr = scope_mh[scope_mh["FundType"].isin(["מחקה", "סל"])].copy()
tr["grp"] = tr["FundType"] + " " + tr["AssetClass"].map(ASSET_LABEL)
a = agg_by(tr, "grp").sort_values("aum_m", ascending=False)
render(a, "grp", "קטגוריה", market_share=True)

# --------------------------- אימות ---------------------------
with st.sidebar.expander("בדיקת אימות (יוני 2026, כל היקום)"):
    ref_month = "2026-06-30"
    if ref_month in months:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = validate(df[df["eom"] == ref_month])
        st.code(buf.getvalue())
        st.success("הכול תואם ✓") if ok else st.error("יש סטייה — בדוק REV_TO_M")
    else:
        st.info(f"חודש הייחוס {ref_month} לא נטען עדיין.")

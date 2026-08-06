"""
שכבת עיבוד: 3 עמודות העזר, KPIs, אגרגציות ואימות מול מספרי הייחוס.
"""

import numpy as np
import pandas as pd

AUM_TO_M = 1_000_000   # fdAUM  -> ₪M
REV_TO_M = 10_000      # תוקן: חלוקה ב-10,000 כי הנתון ב-CSV קטן פי 100 מהצפוי

FUND_TYPES = ["אקטיבית", "סל", "כספית", "מחקה"]
ASSET_LABEL = {"מניות": "מניות", "אגח": 'אג"ח', "סחורה": "סחורה", "קריפטו": "קריפטו"}

# איחוד וריאציות כתיב של אותו מנהל בפועל, לשם אחיד אחד. מפתח = הצורה
# הישנה/החלקית בנתונים, ערך = הצורה שאליה מאחדים. מקום מרכזי יחיד -
# מוחל בתוך add_helper_columns, ומשם משפיע על כל הטבלאות/המסננים/הגרפים.
MANAGER_ALIASES = {
    "אלטשולר": "אלטשולר שחם",
    "תמיר": "תמיר פישמן",
}

# מנהלים שמוסתרים מהתצוגה (טבלאות/גרפים/מסננים) בלי לגעת בקבצי המקור.
# רשימה מרכזית יחידה - קל להוסיף/להסיר ממנה כדי להחזיר מנהל לתצוגה.
EXCLUDED_MANAGERS = {
    "BLACKROCK ASSET",
    "INVESCO INVESTMENT",
}

# מספרי הייחוס (יוני 2026, כל היקום) לאימות עצמי
REFERENCE = {
    "aum_m": 826_511,
    "rev_gross_m": 4148.12,
    "rev_net_m": 3036.39,
    "fee_gross_pct": 0.50,
    "fee_net_pct": 0.37,
    "n_funds": 2478,
}

# ---------------------------------------------------------------------------
# 3 עמודות עזר
# ---------------------------------------------------------------------------
def add_helper_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # איחוד וריאציות שם מנהל + הסתרת מנהלים שהוצאו מהתצוגה - לפני כל
    # אגרגציה, כדי שכל טבלה/מסנן/גרף שמשתמש ב-ManagerCmp יראה תמונה מאוחדת
    df["ManagerCmp"] = df["ManagerCmp"].replace(MANAGER_ALIASES)
    df = df[~df["ManagerCmp"].isin(EXCLUDED_MANAGERS)].copy()

    for c in ["Is_Caspit", "IsKerenSal", "IsTracking"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    # 1) FundType
    def fund_type(r):
        if r["Is_Caspit"] == 1:
            return "כספית"
        if r["IsKerenSal"] == 1:
            return "סל"
        if r["IsTracking"] == 1:
            return "מחקה"
        return "אקטיבית"
    df["FundType"] = df.apply(fund_type, axis=1)

    # 2) IsHosting
    ext = df["Manager_ext"].astype(str).str.strip()
    is_empty = df["Manager_ext"].isna() | (ext == "") | (ext.str.lower() == "nan")
    df["IsHosting"] = np.where(is_empty, "ללא הוסטינג", "הוסטינג")

    # 3) AssetClass
    def asset_class(r):
        sc = "" if pd.isna(r["SuperClass"]) else str(r["SuperClass"])
        sb = "" if pd.isna(r["SubClass"]) else str(r["SubClass"])
        if sc.startswith("מניות"):
            return "מניות"
        if sc.startswith("אג"):
            return "אגח"
        if sc == "סחורות":
            return "סחורה"
        if sc == "נכסים דיגיטליים":
            return "קריפטו"
        if sc == "ממונפות":
            if sb.startswith("מניות"):
                return "מניות"
            if sb.startswith("אג"):
                return "אגח"
            if sb.startswith("סחורה"):
                return "סחורה"
            return "מניות"
        return "מניות"
    df["AssetClass"] = df.apply(asset_class, axis=1)

    return df

# ---------------------------------------------------------------------------
# KPIs ואגרגציות
# ---------------------------------------------------------------------------
def kpis(df: pd.DataFrame) -> dict:
    aum = df["fdAUM"].sum()
    rev = df["Revenues"].sum()
    nrev = df["Net_Revenues"].sum()
    return {
        "aum_m": aum / AUM_TO_M,
        "rev_gross_m": rev / REV_TO_M,
        "rev_net_m": nrev / REV_TO_M,
        "n_funds": int(len(df)),
        # תוקן: הכפלה ב-10000 להתאמה לקנה המידה
        "fee_gross_pct": (rev / aum * 10000) if aum else 0.0,
        "fee_net_pct": (nrev / aum * 10000) if aum else 0.0,
    }

def agg_by(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    g = (
        df.groupby(group_col)
        .agg(aum=("fdAUM", "sum"),
             rev=("Revenues", "sum"),
             nrev=("Net_Revenues", "sum"),
             n=("FundBno", "count"))
        .reset_index()
    )
    total_aum = df["fdAUM"].sum()
    g["aum_m"] = g["aum"] / AUM_TO_M
    g["rev_gross_m"] = g["rev"] / REV_TO_M
    g["rev_net_m"] = g["nrev"] / REV_TO_M
    # תוקן: הכפלה ב-10000
    g["fee_gross_pct"] = g["rev"] / g["aum"] * 10000
    g["fee_net_pct"] = g["nrev"] / g["aum"] * 10000
    g["market_share_pct"] = g["aum"] / total_aum * 100 if total_aum else 0.0
    return g

# ---------------------------------------------------------------------------
# אימות מול מספרי הייחוס
# ---------------------------------------------------------------------------
def validate(df_universe: pd.DataFrame) -> bool:
    k = kpis(df_universe)
    all_ok = True
    for key, ref in REFERENCE.items():
        got = k[key]
        tol = max(abs(ref) * 0.01, 0.01)   # סבילות 1%
        ok = abs(got - ref) <= tol
        all_ok = all_ok and ok
        print(f"{key:16s} got={got:>12,.2f}  ref={ref:>12,.2f}  "
              f"{'OK' if ok else '!!! MISMATCH'}")
    return all_ok
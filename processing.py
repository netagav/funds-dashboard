"""
שכבת עיבוד: 3 עמודות העזר, KPIs, אגרגציות ואימות מול מספרי הייחוס.

יחידות תצוגה (קריטי):
  fdAUM, Revenues, Net_Revenues כולם בשקלים (Revenues נגזר מ-fdAUM),
  ולכן ₪M = חלוקה ב-1,000,000 לכולם.
  זה משחזר את שלושת הייחוסים באופן עקבי:
    נכסים   826,511 ₪M
    הכנסות  4,148.12 ₪M
    דמי ניהול = SUM(Revenues)/SUM(fdAUM)*100 = 0.50%
  (ההערה במסמך על /10000 סותרת את ה-KPI של 0.50% — פונקציית validate תתפוס
   כל בעיה. אם הריצה מראה סטייה, שנה כאן קבוע אחד: REV_TO_M.)
"""

import numpy as np
import pandas as pd

AUM_TO_M = 1_000_000   # fdAUM  -> ₪M
REV_TO_M = 1_000_000   # Revenues / Net_Revenues -> ₪M

FUND_TYPES = ["אקטיבית", "סל", "כספית", "מחקה"]
ASSET_LABEL = {"מניות": "מניות", "אגח": 'אג"ח', "סחורה": "סחורה", "קריפטו": "קריפטו"}

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

    for c in ["Is_Caspit", "IsKerenSal", "IsTracking"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    # 1) FundType - הדדית בלעדי, מכסה 100%. "סל" גובר על "מחקה".
    def fund_type(r):
        if r["Is_Caspit"] == 1:
            return "כספית"
        if r["IsKerenSal"] == 1:
            return "סל"
        if r["IsTracking"] == 1:
            return "מחקה"
        return "אקטיבית"
    df["FundType"] = df.apply(fund_type, axis=1)

    # 2) IsHosting - Manager_ext ריק => ללא הוסטינג
    ext = df["Manager_ext"].astype(str).str.strip()
    is_empty = df["Manager_ext"].isna() | (ext == "") | (ext.str.lower() == "nan")
    df["IsHosting"] = np.where(is_empty, "ללא הוסטינג", "הוסטינג")

    # 3) AssetClass - רלוונטי רק למחקה/סל
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
        "fee_gross_pct": (rev / aum * 100) if aum else 0.0,   # ממוצע משוקלל
        "fee_net_pct": (nrev / aum * 100) if aum else 0.0,     # ממוצע משוקלל
    }


def agg_by(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """אגרגציה לפי עמודה. נתח שוק מחושב מתוך סך הנכסים של ה-df שהועבר."""
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
    g["fee_gross_pct"] = g["rev"] / g["aum"] * 100
    g["fee_net_pct"] = g["nrev"] / g["aum"] * 100
    g["market_share_pct"] = g["aum"] / total_aum * 100 if total_aum else 0.0
    return g


# ---------------------------------------------------------------------------
# אימות מול מספרי הייחוס
# ---------------------------------------------------------------------------
def validate(df_universe: pd.DataFrame) -> bool:
    """מריצים על יוני 2026 כל היקום. מדפיס got מול ref לכל KPI."""
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

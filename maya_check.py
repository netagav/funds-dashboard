"""
maya_check.py — השוואת רשימת הקרנות מול אתר המאיה (TASE), ללא SQL.

הרעיון: רשימת הקרנות של החודש כבר יושבת ב-CSV שנדחף לגיט, ולכן ההשוואה מול
המאיה לא צריכה גישה ל-SQL — היא רצה מכל מקום עם אינטרנט.

הפרדה מכוונת בין הורדה להשוואה (כי המאיה עלולה לחסום IP של שרתים):
    download_maya()        -> מוריד חי מהמאיה (עובד מהבית; אולי לא מהענן)
    load_maya_file(path)   -> קורא קובץ מאיה שכבר הורד ונשמר בגיט (תמיד עובד)
    reconcile(a, b)        -> משווה שני DataFrames, בלי רשת

שימוש כמודול (בדשבורד):
    from maya_check import download_maya, reconcile
    result = reconcile(month_df, download_maya())

שימוש כסקריפט (GitHub Actions / הרצה ידנית):
    python maya_check.py            # משווה את החודש האחרון וכותב דוחות ל-data/reports/
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pandas as pd
import requests

MAYA_API_URL = "https://maya.tase.co.il/api/v1/funds/file"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = DATA_DIR / "reports"

FUND_COL_MAYA = "מס' קרן"      # עמודת מספר הקרן בקובץ המאיה
FUND_COL_SQL = "FundBno"       # עמודת מספר הקרן ב-CSV שלנו


# ---------------------------------------------------------------------------
# עזרי ניקוי
# ---------------------------------------------------------------------------
def _clean_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.replace("\n", " ", regex=False)
        .str.replace("\r", " ", regex=False)
        .str.strip()
    )
    return df


def _add_fund_number(df: pd.DataFrame) -> pd.DataFrame:
    if FUND_COL_MAYA not in df.columns:
        raise KeyError(
            f'עמודת "{FUND_COL_MAYA}" לא נמצאה בקובץ המאיה. '
            f"עמודות שהתקבלו: {df.columns.tolist()}"
        )
    df = df.copy()
    df["FundNumber"] = pd.to_numeric(df[FUND_COL_MAYA], errors="coerce").astype("Int64")
    return df


def _maya_headers() -> dict:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
        "Content-Type": "application/json",
        "Origin": "https://maya.tase.co.il",
        "Referer": "https://maya.tase.co.il/he/funds/all",
        "Connection": "keep-alive",
    }


# ---------------------------------------------------------------------------
# הורדה / טעינה
# ---------------------------------------------------------------------------
def download_maya(timeout: int = 120, save_to: Path | None = None) -> pd.DataFrame:
    """מוריד חי את קובץ הקרנות מהמאיה. מחזיר DataFrame עם עמודת FundNumber.
    אם save_to מסופק — שומר גם עותק גולמי (שימושי לשמירה בגיט)."""
    for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        os.environ.pop(var, None)

    resp = requests.post(MAYA_API_URL, headers=_maya_headers(), json={}, timeout=timeout)
    resp.raise_for_status()
    if not resp.content:
        raise RuntimeError("המאיה החזירה תגובה ריקה.")

    if save_to is not None:
        save_to.parent.mkdir(parents=True, exist_ok=True)
        save_to.write_bytes(resp.content)

    try:
        df = pd.read_csv(io.BytesIO(resp.content), encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(io.BytesIO(resp.content), encoding="windows-1255")

    return _add_fund_number(_clean_cols(df))


def load_maya_file(path: str | Path) -> pd.DataFrame:
    """קורא קובץ מאיה שכבר הורד ונשמר (למשל data/maya/maya_YYYY-MM-DD.csv).
    מסלול הגיבוי כשאין הורדה חיה מהענן."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"קובץ מאיה לא נמצא: {path}")
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="windows-1255")
    return _add_fund_number(_clean_cols(df))


# ---------------------------------------------------------------------------
# ההשוואה (ללא רשת)
# ---------------------------------------------------------------------------
def reconcile(month_df: pd.DataFrame, maya_df: pd.DataFrame) -> dict:
    """משווה את רשימת הקרנות של החודש (FundBno) מול רשימת הקרנות במאיה (FundNumber).
    מחזיר dict: summary, sql_not_maya, maya_not_sql, counts."""
    sql_funds = set(
        pd.to_numeric(month_df[FUND_COL_SQL], errors="coerce").dropna().astype(int)
    )
    maya_funds = set(maya_df["FundNumber"].dropna().astype(int))

    both = sql_funds & maya_funds
    sql_not_maya = sorted(sql_funds - maya_funds)
    maya_not_sql = sorted(maya_funds - sql_funds)

    counts = {
        "sql_funds": len(sql_funds),
        "maya_funds": len(maya_funds),
        "in_both": len(both),
        "sql_not_maya": len(sql_not_maya),
        "maya_not_sql": len(maya_not_sql),
    }
    summary = pd.DataFrame({
        "מדד": [
            "קרנות ב-SQL (החודש)", "קרנות במאיה", "קרנות בשני המקורות",
            "ב-SQL ולא במאיה", "במאיה ולא ב-SQL",
        ],
        "כמות": [
            counts["sql_funds"], counts["maya_funds"], counts["in_both"],
            counts["sql_not_maya"], counts["maya_not_sql"],
        ],
    })
    return {
        "summary": summary,
        "sql_not_maya": pd.DataFrame({"FundNumber": sql_not_maya}),
        "maya_not_sql": pd.DataFrame({"FundNumber": maya_not_sql}),
        "counts": counts,
    }


# ---------------------------------------------------------------------------
# הרצה כסקריפט (GitHub Actions / ידני)
# ---------------------------------------------------------------------------
def _latest_month_df() -> tuple[pd.DataFrame, str]:
    from data_source import load_data  # ייבוא רק בהרצת סקריפט
    df = load_data()
    latest = sorted(df["eom"].unique())[-1]
    return df[df["eom"] == latest].copy(), latest


def main() -> int:
    month_df, eom = _latest_month_df()
    print(f"החודש האחרון: {eom}  ({len(month_df):,} קרנות)")

    try:
        maya_df = download_maya(save_to=DATA_DIR / "maya" / f"maya_{eom}.csv")
    except Exception as exc:  # noqa: BLE001
        print(f"הורדת המאיה נכשלה: {exc}", file=sys.stderr)
        fallback = DATA_DIR / "maya" / f"maya_{eom}.csv"
        if fallback.exists():
            print(f"משתמש בעותק שמור: {fallback}")
            maya_df = load_maya_file(fallback)
        else:
            return 1

    print(f"מאיה: {len(maya_df):,} שורות")
    result = reconcile(month_df, maya_df)
    print(result["summary"].to_string(index=False))

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    result["summary"].to_csv(REPORTS_DIR / f"maya_summary_{eom}.csv",
                             index=False, encoding="utf-8-sig")
    result["sql_not_maya"].to_csv(REPORTS_DIR / f"maya_sql_not_maya_{eom}.csv",
                                  index=False, encoding="utf-8-sig")
    result["maya_not_sql"].to_csv(REPORTS_DIR / f"maya_maya_not_sql_{eom}.csv",
                                  index=False, encoding="utf-8-sig")
    print(f"דוחות נכתבו ל-{REPORTS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
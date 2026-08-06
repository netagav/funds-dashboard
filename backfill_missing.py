"""
backfill_missing.py — השלמת שורות עם ShortName ריק מהחודש הקודם בפועל.

רלוונטי רק לקבצים חדשים שנכנסים מעכשיו והלאה. לא מתקן רטרואקטיבית קבצים
היסטוריים קיימים (הסקריפט פועל תמיד רק על הקובץ עם ה-eom המקסימלי שנמצא
כרגע ב-data/, כלומר הקובץ שנכנס לאחרונה - לא על העבר).

הבעיה: לפעמים קרן מופיעה בקובץ החודש עם fdAUM אמיתי אבל בלי מידע סטטי
(ShortName, SubClass, ManagerCmp וכו') - כנראה עדכון שהגיע ממקור אחד
(AUM) לפני שהגיע מהמקור השני (המידע הסטטי). הפתרון: לשחזר את המידע
הסטטי מהחודש הקודם בפועל של אותה קרן (FundBno), ולחשב מחדש את
Revenues / Net_Fees / Net_Revenues מול ה-fdAUM האמיתי של החודש הנוכחי.

שימוש כמודול (כרשת ביטחון, למשל מתוך data_source.py - רק על החודש
האחרון שנטען, לא על כל ההיסטוריה):
    from backfill_missing import backfill_missing_shortname
    df = backfill_missing_shortname(latest_eom, df, df)

שימוש כסקריפט (ב-GitHub Action, לפני refresh_maya.py / maya_check.py):
    python backfill_missing.py
מאתר לבד את הקובץ עם ה-eom הגדול ביותר מבין data/funds_*.csv (=הקובץ
שנכנס לאחרונה), משחזר בו שורות עם ShortName ריק, ושומר את הקובץ
בחזרה רק אם היה שינוי בפועל.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# עמודות שלעולם לא נדרסות בשחזור - מגיעות כפי שהן מהקובץ החדש
PROTECTED_COLS = {"FundBno", "eom", "fdAUM"}

# עמודות נגזרות - לא מועתקות מהחודש הקודם, אלא מחושבות מחדש בהמשך
DERIVED_COLS = {"Revenues", "Net_Fees", "Net_Revenues"}


# ---------------------------------------------------------------------------
# הליבה - משותפת לשימוש כמודול (data_source.py) וכסקריפט (CI)
# ---------------------------------------------------------------------------
def find_previous_month_data(history_df: pd.DataFrame, eom: str) -> pd.DataFrame:
    """מאתר בתוך history_df את שורות 'החודש הקודם בפועל' ל-eom הנתון -
    ה-eom הגדול ביותר שקטן מ-eom. history_df יכול להיות איחוד של קבצים
    חודשיים ו/או שנתיים; אין הנחה שהחודש הקודם יושב דווקא בקובץ נפרד -
    האיתור נעשה לפי ערכי eom בפועל, לא לפי שמות קבצים."""
    earlier = history_df[history_df["eom"] < eom]
    if earlier.empty:
        return earlier
    prev_eom = earlier["eom"].max()
    return earlier[earlier["eom"] == prev_eom]


def backfill_missing_shortname(
    eom: str, df_new: pd.DataFrame, history_df: pd.DataFrame
) -> pd.DataFrame:
    """
    משחזר שורות עם ShortName ריק/NaN בחודש eom מתוך df_new, לפי הנתונים
    של אותה קרן (FundBno) בחודש הקודם בפועל (מתוך history_df).

    לשורה שמשוחזרת: כל העמודות מוחלפות בערכי החודש הקודם - כולל דריסה
    מלאה של תאים שכבר מלאים בקובץ החדש - פרט ל-FundBno / eom / fdAUM
    שנשארים בדיוק כפי שהגיעו בקובץ החדש. Revenues / Net_Fees /
    Net_Revenues לא מועתקות מהחודש הקודם - הן מחושבות מחדש מ-ManagerFee
    ו-DistClassificationVal המשוחזרים, מול ה-fdAUM הנוכחי (שלא השתנה).

    שורה שבה ShortName מלא - לא נוגעים בה כלל, גם אם יש בה תאים ריקים
    אחרים. FundBno שלא נמצא בחודש הקודם - השורה נשארת כפי שהיא.
    """
    out = df_new.copy()

    target_mask = out["eom"] == eom
    short = out["ShortName"]
    missing_mask = target_mask & (short.isna() | (short.astype(str).str.strip() == ""))

    if not missing_mask.any():
        return out

    prev = find_previous_month_data(history_df, eom)
    if prev.empty:
        return out

    prev_by_fund = (
        prev.dropna(subset=["FundBno"])
        .drop_duplicates(subset=["FundBno"], keep="last")
        .set_index("FundBno")
    )

    restore_cols = [
        c for c in out.columns
        if c not in PROTECTED_COLS and c not in DERIVED_COLS
    ]

    for idx in out.index[missing_mask]:
        fb = out.at[idx, "FundBno"]
        if fb not in prev_by_fund.index:
            continue  # אין ממה לשחזר - השורה נשארת כפי שהיא

        prev_row = prev_by_fund.loc[fb]
        for col in restore_cols:
            if col in prev_row.index:
                out.at[idx, col] = prev_row[col]

        # חישוב מחדש של העמודות הנגזרות מול ה-fdAUM האמיתי של החודש הנוכחי
        aum = out.at[idx, "fdAUM"]
        mgr_fee = out.at[idx, "ManagerFee"]
        dist = out.at[idx, "DistClassificationVal"]
        if pd.notna(mgr_fee) and pd.notna(aum):
            out.at[idx, "Revenues"] = (mgr_fee / 100) * aum
        if pd.notna(mgr_fee) and pd.notna(dist):
            net_fee = mgr_fee - dist
            out.at[idx, "Net_Fees"] = net_fee
            if pd.notna(aum):
                out.at[idx, "Net_Revenues"] = (net_fee / 100) * aum

    return out


# ---------------------------------------------------------------------------
# הרצה כסקריפט: מאתר לבד את הקובץ החדש מתוך data/funds_*.csv
# ---------------------------------------------------------------------------
def _read_raw_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="windows-1255")


def _normalized_eom(df: pd.DataFrame) -> pd.Series:
    """אותה נורמליזציה בדיוק כמו ב-data_source.load_data, כדי שהשוואות
    תאריכים בין קבצים עם פורמטים לא-עקביים (יום/חודש/שנה מול חודש/יום/שנה)
    יעבדו נכון."""
    return pd.to_datetime(
        df["eom"], format="mixed", dayfirst=True, errors="coerce"
    ).dt.strftime("%Y-%m-%d")


def _all_funds_files() -> list[Path]:
    return sorted(DATA_DIR.glob("funds_*.csv"))


def main() -> int:
    files = _all_funds_files()
    if not files:
        print(f"לא נמצאו קבצי funds_*.csv בתוך {DATA_DIR}.")
        return 1

    raw_by_path: dict[Path, pd.DataFrame] = {}
    norm_by_path: dict[Path, pd.DataFrame] = {}
    for path in files:
        raw = _read_raw_csv(path)
        norm = raw.copy()
        norm["eom"] = _normalized_eom(raw)
        raw_by_path[path] = raw
        norm_by_path[path] = norm

    # הקובץ החדש = זה עם ה-eom המקסימלי מבין כל הקבצים - לא מניחים
    # שם קובץ מסוים, רק בודקים בפועל מי מכיל את התאריך המאוחר ביותר.
    target_path = max(norm_by_path, key=lambda p: norm_by_path[p]["eom"].max())
    target_norm = norm_by_path[target_path]
    target_raw = raw_by_path[target_path]
    target_eom = target_norm["eom"].max()

    history_df = pd.concat(norm_by_path.values(), ignore_index=True)

    target_rows = target_norm["eom"] == target_eom
    short = target_norm["ShortName"]
    missing_before = target_rows & (short.isna() | (short.astype(str).str.strip() == ""))
    n_before = int(missing_before.sum())

    print(f"קובץ חדש שזוהה: {target_path.name}  (eom={target_eom})")
    print(f"שורות עם ShortName ריק בחודש זה: {n_before}")

    if n_before == 0:
        print("אין מה לשחזר.")
        return 0

    fixed = backfill_missing_shortname(target_eom, target_norm, history_df)
    fixed["eom"] = target_raw["eom"].values  # שימור פורמט התאריך המקורי בקובץ

    short_after = fixed["ShortName"]
    missing_after = target_rows & (
        short_after.isna() | (short_after.astype(str).str.strip() == "")
    )
    n_fixed = n_before - int(missing_after.sum())

    print(f"שורות ששוחזרו מהחודש הקודם: {n_fixed}")

    if n_fixed == 0:
        print("לא נמצאו נתונים תואמים בחודש הקודם - לא שומר שינויים.")
        return 0

    fixed.to_csv(target_path, index=False, encoding="utf-8-sig")
    print(f"נשמר: {target_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

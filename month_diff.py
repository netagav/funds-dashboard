"""
month_diff.py — השוואת קרנות בין שני חודשים בנתונים שלך (מי נכנס / מי יצא),
עם הצלבה אופציונלית מול המאיה כשכבת נכונות נוספת.

הליבה מדויקת ומיושרת-תאריך: מבוססת כולה על ה-CSV-ים החודשיים שלך.
    קרן שהייתה בחודש הישן ואיננה בחדש  -> יצאה (פורקה/נסגרה)
    קרן שבחודש החדש ולא הייתה בישן       -> נכנסה (חדשה)

ההצלבה מול המאיה (אופציונלית) היא אינדיקציה רכה בלבד — המאיה היא תמונת מצב
של היום ולא מיושרת לתאריך החודש.

שימוש כמודול (בדשבורד):
    from month_diff import available_months, month_diff, cross_check_with_maya
    d = month_diff(df, "2026-06-30", "2026-07-31")
    d = cross_check_with_maya(d, maya_df)   # אופציונלי

שימוש כסקריפט (בדיקה מהטרמינל):
    python month_diff.py
"""

from __future__ import annotations

import sys

import pandas as pd

FUND_ID = "FundBno"
DESC_COLS = ["FundBno", "ShortName", "ManagerCmp", "SuperClass", "fdAUM"]


def available_months(df: pd.DataFrame) -> list[str]:
    return sorted(df["eom"].dropna().unique().tolist())


def _ids(frame: pd.DataFrame) -> set[int]:
    return set(pd.to_numeric(frame[FUND_ID], errors="coerce").dropna().astype(int))


def _slice(df: pd.DataFrame, month: str, ids: set[int]) -> pd.DataFrame:
    cols = [c for c in DESC_COLS if c in df.columns]
    frame = df[df["eom"] == month].copy()
    keep = pd.to_numeric(frame[FUND_ID], errors="coerce").isin(ids)
    return (
        frame[keep][cols]
        .drop_duplicates(subset=[FUND_ID])
        .sort_values(FUND_ID)
        .reset_index(drop=True)
    )


def month_diff(df: pd.DataFrame, month_old: str, month_new: str) -> dict:
    """מחזיר dict: entered (מהחודש החדש), exited (מהחודש הישן), counts."""
    old = df[df["eom"] == month_old]
    new = df[df["eom"] == month_new]
    if old.empty or new.empty:
        raise ValueError(
            f"אחד החודשים ריק — old={month_old} ({len(old)} שורות), "
            f"new={month_new} ({len(new)} שורות)."
        )
    old_ids, new_ids = _ids(old), _ids(new)
    return {
        "exited": _slice(df, month_old, old_ids - new_ids),   # מידע מהחודש הישן
        "entered": _slice(df, month_new, new_ids - old_ids),  # מידע מהחודש החדש
        "counts": {
            "exited": len(old_ids - new_ids),
            "entered": len(new_ids - old_ids),
            "old_total": len(old_ids),
            "new_total": len(new_ids),
        },
    }


def cross_check_with_maya(diff_result: dict, maya_df: pd.DataFrame) -> dict:
    """מוסיף לכל טבלה עמודת 'במאיה_החודש' + פרשנות רכה.
    המאיה = תמונת מצב עדכנית, ולכן זו אינדיקציה, לא הוכחה."""
    maya_ids = set(maya_df["FundNumber"].dropna().astype(int))

    def annotate(frame: pd.DataFrame, kind: str) -> pd.DataFrame:
        f = frame.copy()
        if f.empty:
            f["במאיה_החודש"] = pd.Series(dtype="boolean")
            f["פרשנות"] = pd.Series(dtype="string")
            return f
        f["במאיה_החודש"] = (
            pd.to_numeric(f[FUND_ID], errors="coerce").astype("Int64").isin(maya_ids)
        )
        if kind == "exited":
            mapping = {
                True: "עדיין במאיה של החודש — ייתכן שהצילום החדש פספס",
                False: "גם לא במאיה — עקבי עם פירוק/סגירה",
            }
        else:  # entered
            mapping = {
                True: "קיימת במאיה של החודש — עקבי עם קרן חדשה",
                False: "לא במאיה — לבדוק",
            }
        f["פרשנות"] = f["במאיה_החודש"].map(mapping)
        return f

    return {
        "exited": annotate(diff_result["exited"], "exited"),
        "entered": annotate(diff_result["entered"], "entered"),
        "counts": diff_result["counts"],
    }


def main() -> int:
    from data_source import load_data
    df = load_data()
    months = available_months(df)
    print(f"חודשים זמינים: {months}")
    if len(months) < 2:
        print("צריך לפחות שני חודשים כדי להשוות. יהיה זמין כשייכנס החודש הבא.")
        return 0
    d = month_diff(df, months[-2], months[-1])
    print(f"\n{months[-2]} -> {months[-1]}")
    print(f"יצאו: {d['counts']['exited']}  |  נכנסו: {d['counts']['entered']}")
    print("\n-- יצאו --")
    print(d["exited"].to_string(index=False) if not d["exited"].empty else "(אין)")
    print("\n-- נכנסו --")
    print(d["entered"].to_string(index=False) if not d["entered"].empty else "(אין)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
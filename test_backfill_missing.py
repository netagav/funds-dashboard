"""
טסט/דוגמה קטנים ל-backfill_missing_shortname.

מריצים ישירות:  python test_backfill_missing.py
או עם pytest:    pytest test_backfill_missing.py
"""

import numpy as np
import pandas as pd

from backfill_missing import backfill_missing_shortname

COLUMNS = [
    "FundBno", "ShortName", "SubClass", "MainClass", "SuperClass", "eom",
    "fdAUM", "ManagerCmp", "Manager_ext", "IsTracking", "IsKerenSal",
    "ManagerFee", "DistClassificationVal", "Revenues", "Net_Fees",
    "Net_Revenues", "Is_Caspit",
]


def _row(**kwargs):
    base = {c: np.nan for c in COLUMNS}
    base.update(kwargs)
    return base


def _frame(rows):
    # dtype=object מדמה עמודת טקסט אמיתית שנקראה מ-CSV (יש בה גם ערכים
    # מספריים וגם ריקים/מחרוזות) - כדי לא לקבל אזהרת dtype מהמבנה
    # המלאכותי של שורה בודדת שכל תאיה NaN.
    return pd.DataFrame(rows).astype(object)


def test_backfill_restores_row_and_recomputes_revenues():
    """שורה עם FundBno קיים, ShortName ריק, ושאר העמודות חלקן 'זבל'
    וחלקן ריקות - אחרי הפעלת הפונקציה כל העמודות (פרט ל-FundBno/eom/
    fdAUM) שוות לערכים מהחודש הקודם, ו-fdAUM לא השתנה."""
    prev = _frame([
        _row(
            FundBno=123456, ShortName="קרן לדוגמה", SubClass="מניות",
            MainClass="מניות בארץ", SuperClass="מניות בארץ", eom="2026-05-31",
            fdAUM=1_000_000.0, ManagerCmp="חברה א", Manager_ext=1.0,
            IsTracking=True, IsKerenSal=False, ManagerFee=0.5,
            DistClassificationVal=0.1, Revenues=5_000.0, Net_Fees=0.4,
            Net_Revenues=4_000.0, Is_Caspit=0,
        ),
    ])

    new = _frame([
        _row(  # השורה לשחזור: ShortName ריק, שאר התאים חלק "זבל" חלק ריקים
            FundBno=123456, ShortName=np.nan, SubClass="ZZZ_GARBAGE",
            MainClass=np.nan, SuperClass=np.nan, eom="2026-06-30",
            fdAUM=2_500_000.0, ManagerCmp="ZZZ", Manager_ext=np.nan,
            IsTracking=np.nan, IsKerenSal=np.nan, ManagerFee=999.0,
            DistClassificationVal=999.0, Revenues=np.nan, Net_Fees=np.nan,
            Net_Revenues=np.nan, Is_Caspit=np.nan,
        ),
    ])

    history = pd.concat([prev, new], ignore_index=True)

    fixed = backfill_missing_shortname("2026-06-30", new, history)
    row = fixed.iloc[0]

    # FundBno / eom / fdAUM - נשארים כפי שהגיעו בקובץ החדש
    assert row["FundBno"] == 123456
    assert row["eom"] == "2026-06-30"
    assert row["fdAUM"] == 2_500_000.0

    # שאר העמודות - משוחזרות מהחודש הקודם, כולל דריסה מלאה
    restored_from_prev = {
        "ShortName": "קרן לדוגמה", "SubClass": "מניות", "MainClass": "מניות בארץ",
        "SuperClass": "מניות בארץ", "ManagerCmp": "חברה א", "Manager_ext": 1.0,
        "IsTracking": True, "IsKerenSal": False, "ManagerFee": 0.5,
        "DistClassificationVal": 0.1, "Is_Caspit": 0,
    }
    for col, expected in restored_from_prev.items():
        assert row[col] == expected, f"{col}: expected {expected!r}, got {row[col]!r}"

    # Revenues/Net_Fees/Net_Revenues - מחושבות מחדש מול fdAUM הנוכחי (2.5M),
    # לא מועתקות ישירות מהחודש הקודם (5000/0.4/4000)
    assert row["Revenues"] == (0.5 / 100) * 2_500_000.0
    assert row["Net_Fees"] == 0.5 - 0.1
    assert row["Net_Revenues"] == ((0.5 - 0.1) / 100) * 2_500_000.0


def test_row_with_shortname_untouched():
    """שורה עם ShortName מלא לא נוגעים בה, גם אם יש בה תאים ריקים אחרים."""
    new = _frame([
        _row(FundBno=1, ShortName="קרן קיימת", SubClass=np.nan,
             eom="2026-06-30", fdAUM=10.0),
    ])
    fixed = backfill_missing_shortname("2026-06-30", new, new)
    assert fixed.iloc[0].equals(new.iloc[0])


def test_fund_not_in_previous_month_left_as_is():
    """FundBno שלא נמצא בחודש הקודם - השורה נשארת כמו שהיא."""
    prev = _frame([_row(FundBno=999, ShortName="אחר", eom="2026-05-31", fdAUM=1.0)])
    new = _frame([_row(FundBno=1, ShortName=np.nan, eom="2026-06-30", fdAUM=5.0)])
    history = pd.concat([prev, new], ignore_index=True)

    fixed = backfill_missing_shortname("2026-06-30", new, history)

    assert pd.isna(fixed.iloc[0]["ShortName"])
    assert fixed.iloc[0]["fdAUM"] == 5.0


def test_previous_month_found_inside_bundled_history_not_only_separate_file():
    """הפונקציה 'הכללית' - לא מניחה שהחודש הקודם יושב בקובץ נפרד. מדמים
    את זה על ידי history_df אחד שמכיל כמה חודשים יחד (כמו קובץ שנתי
    מאוחד), ובודקים שהחודש הקודם בפועל (המקסימלי שקטן מה-eom הנוכחי)
    נמצא נכון גם כשהוא לא בקובץ החדש עצמו."""
    bundled_history = _frame([
        _row(FundBno=7, ShortName="ישנה", eom="2026-04-30", fdAUM=1.0),
        _row(FundBno=7, ShortName="עדכנית יותר", SubClass="אג\"ח",
             eom="2026-05-31", fdAUM=2.0),
    ])
    new = _frame([
        _row(FundBno=7, ShortName=np.nan, eom="2026-06-30", fdAUM=3.0),
    ])

    fixed = backfill_missing_shortname("2026-06-30", new, bundled_history)

    assert fixed.iloc[0]["ShortName"] == "עדכנית יותר"
    assert fixed.iloc[0]["SubClass"] == "אג\"ח"
    assert fixed.iloc[0]["fdAUM"] == 3.0  # לא הוחלף בערך של אף אחד מהחודשים הקודמים


if __name__ == "__main__":
    test_backfill_restores_row_and_recomputes_revenues()
    test_row_with_shortname_untouched()
    test_fund_not_in_previous_month_left_as_is()
    test_previous_month_found_inside_bundled_history_not_only_separate_file()
    print("כל הטסטים עברו ✓")

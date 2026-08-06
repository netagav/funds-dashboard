"""
שכבת מקור נתונים.

USE_SQL = False  -> קורא את כל קבצי data/funds_*.csv (פיתוח מהבית / פריסה בענן)
USE_SQL = True   -> מושך את החודש האחרון מ-SQL (רק במשרד, עם ODBC + Windows Auth)

מעבר בין המצבים = שינוי של מילה אחת.
בפריסה ל-Streamlit Cloud משאירים USE_SQL = False (הענן לא מגיע ל-SQL).
"""

import os
import glob
import pandas as pd

from backfill_missing import backfill_missing_shortname

USE_SQL = False

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# 17 עמודות המקור מ-SQL (לתיעוד / אימות סכימה)
RAW_COLUMNS = [
    "FundBno", "ShortName", "SubClass", "MainClass", "SuperClass", "eom",
    "fdAUM", "ManagerCmp", "Manager_ext", "IsTracking", "IsKerenSal",
    "ManagerFee", "DistClassificationVal", "Revenues", "Net_Fees",
    "Net_Revenues", "Is_Caspit",
]

# ---------------------------------------------------------------------------
# הדבק כאן את השאילתה העובדת שלך (זו שכבר בנית ב-Power Query / SQL).
# היא כבר מחשבת Revenues / Net_Fees / Net_Revenues / Is_Caspit, ומושכת רק
# את החודש האחרון עם WHERE eom = (SELECT MAX(eom) FROM FundsMonthlyData).
# ---------------------------------------------------------------------------
SQL_QUERY = r"""
-- <<< הדבק כאן את ה-SELECT המלא שלך שממזג vFundsInfo + FundsMonthlyData >>>
-- דוגמה לשלד בלבד:
-- SELECT i.FundBno, i.ShortName, i.SubClass, i.MainClass, i.SuperClass,
--        m.eom, m.fdAUM, i.ManagerCmp, i.Manager_ext, i.IsTracking, i.IsKerenSal,
--        i.ManagerFee, i.DistClassificationVal,
--        (i.ManagerFee/100.0) * m.fdAUM                                   AS Revenues,
--        (i.ManagerFee - i.DistClassificationVal)                        AS Net_Fees,
--        ((i.ManagerFee - i.DistClassificationVal)/100.0) * m.fdAUM       AS Net_Revenues,
--        CASE WHEN i.SuperClass = N'קרן כספית' THEN 1 ELSE 0 END          AS Is_Caspit
-- FROM vFundsInfo i
-- JOIN FundsMonthlyData m ON m.FundBno = i.FundBno
-- WHERE m.eom = (SELECT MAX(eom) FROM FundsMonthlyData);
"""


def _load_from_csv() -> pd.DataFrame:
    """קורא את כל קבצי החודשים מ-data/ ומאחד לטבלת היסטוריה אחת."""
    files = sorted(glob.glob(os.path.join(DATA_DIR, "funds_*.csv")))
    if not files:
        raise FileNotFoundError(
            f"לא נמצאו קבצים בתבנית funds_*.csv בתוך {DATA_DIR}. "
            "ודא שהעלית לפחות חודש אחד."
        )
    frames = [pd.read_csv(f) for f in files]
    df = pd.concat(frames, ignore_index=True)
    # רשת ביטחון: הסרת כפילויות לפי (FundBno, eom), שמירת האחרון שנכתב
    df = df.drop_duplicates(subset=["FundBno", "eom"], keep="last")
    return df


def _load_from_sql() -> pd.DataFrame:
    """מושך את החודש האחרון מ-SQL. פועל רק במשרד (Windows Auth + ODBC Driver 17)."""
    import urllib.parse
    from sqlalchemy import create_engine  # ייבוא עצל - לא נדרש בבית

    conn_str = (
        "Driver={ODBC Driver 17 for SQL Server};"
        r"Server=MSH-MQ\ESCONDIDA;"
        "Database=MQDB;"
        "Trusted_Connection=yes;"
    )
    engine = create_engine(
        "mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(conn_str)
    )
    with engine.connect() as conn:
        df = pd.read_sql(SQL_QUERY, conn)
    return df


def load_data() -> pd.DataFrame:
    """נקודת כניסה יחידה. מחזיר DataFrame עם 17 עמודות המקור."""
    df = _load_from_sql() if USE_SQL else _load_from_csv()

    # נרמול eom למחרוזת 'YYYY-MM-DD' כדי שהמסנן יעבוד עקבי
    df["eom"] = pd.to_datetime(
        df["eom"], format="mixed", dayfirst=True, errors="coerce"
    ).dt.strftime("%Y-%m-%d")

    if df["eom"].isna().any():
        n_bad = df["eom"].isna().sum()
        print(f"אזהרה: {n_bad} שורות עם eom לא-תקין הפכו ל-NaT")

    # ודא שהעמדות המספריות אכן מספריות
    for c in ["fdAUM", "ManagerFee", "DistClassificationVal",
              "Revenues", "Net_Fees", "Net_Revenues"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # רשת ביטחון: השלמת שורות עם ShortName ריק בחודש האחרון בלבד (מול
    # החודש שלפניו) - לקבצים שהוזנו בלי לעבור דרך ה-GitHub Action. לא
    # נוגעת בשאר ההיסטוריה בכל rerun.
    latest_eom = df["eom"].max()
    if pd.notna(latest_eom):
        df = backfill_missing_shortname(latest_eom, df, df)

    return df

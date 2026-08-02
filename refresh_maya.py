"""
refresh_maya.py — הורדת snapshot של המאיה לחודש האחרון, פעם בחודש, מהבית.

מוריד רק אם עדיין אין קובץ לחודש האחרון (כדי שה-snapshot יישאר "קפוא").
אחרי ההרצה: git add data/maya && git commit && git push

שגרה חודשית:
    1. נכנס קובץ funds_<eom>.csv חדש (דרך Make).
    2. מהבית: git pull, ואז  python refresh_maya.py
    3. git add data/maya && git commit -m "maya snapshot" && git push
"""

from pathlib import Path

from data_source import load_data
from maya_check import download_maya

MAYA_DIR = Path(__file__).resolve().parent / "data" / "maya"


def main() -> int:
    df = load_data()
    eom = sorted(df["eom"].unique())[-1]
    path = MAYA_DIR / f"maya_{eom}.csv"

    if path.exists():
        print(f"כבר קיים snapshot לחודש {eom}:\n  {path}\nלא מוריד שוב (קפוא).")
        return 0

    print(f"מוריד snapshot של המאיה לחודש {eom} ...")
    maya_df = download_maya(save_to=path)
    print(f"נשמר: {path}  ({len(maya_df):,} שורות)")
    print("עכשיו:  git add data/maya && git commit -m \"maya snapshot\" && git push")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
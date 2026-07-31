# דשבורד קרנות — Streamlit

## מבנה
```
funds-dashboard/
├── app.py            # ממשק: KPIs + 4 טבלאות + 3 מסננים
├── data_source.py    # מתג USE_SQL: CSV (בית/ענן) או SQL (משרד)
├── processing.py     # 3 עמודות עזר, KPIs, אגרגציות, אימות
├── requirements.txt
└── data/             # קובץ CSV לכל חודש: funds_YYYY-MM-DD.csv
```

## הרצה מקומית (בבית)
```bash
pip install -r requirements.txt
streamlit run app.py
```
`USE_SQL = False` — קורא את כל `data/funds_*.csv`, מאחד ומסיר כפילויות לפי (FundBno, eom).

## שגרה חודשית
1. במשרד: רענן את שאילתת החודש הבודד → שמור כ‑`funds_<eom>.csv` → שלח במייל לתיבה הייעודית.
2. Make קולט את המייל ומבצע commit ל‑`data/` ב‑GitHub.
3. Streamlit Cloud מתרנדר מחדש אוטומטית.

## אימות
פתח את "בדיקת אימות" ב‑sidebar (או הרץ `validate()` מ‑processing) וודא מול הייחוס:
נכסים 826,511 ₪M · הכנסות 4,148.12 ₪M · דמי ניהול 0.50% · 2,478 קרנות.

## הערת יחידות
נכסים והכנסות שניהם בשקלים → ₪M = חלוקה ב‑1,000,000 לשניהם. אם האימות מראה סטייה,
שנה את הקבוע `REV_TO_M` ב‑`processing.py` (מקום אחד).

# 💳 דשבורד הוצאות אשראי

ניתוח חכם של פירוט כרטיס אשראי כאל — מ-PDF לדשבורד אנליטי בשניות.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![Streamlit](https://img.shields.io/badge/UI-Streamlit-red) ![License](https://img.shields.io/badge/License-Personal-lightgrey)

---

## מה זה עושה?

מעלים קובץ PDF של פירוט כרטיס אשראי כאל → האפליקציה מחלצת את כל העסקאות אוטומטית → ומציגה דשבורד אינטראקטיבי:

| פיצ'ר | תיאור |
|---|---|
| **חילוץ PDF** | קריאת קבצי פירוט כאל, כולל תיקון עברית RTL אוטומטי |
| **KPI cards** | סה"כ הוצאות, ממוצע חודשי, מספר עסקאות |
| **גרף עוגה** | התפלגות הוצאות לפי קטגוריה (אינטראקטיבי) |
| **ספקים מובילים** | Top 8 בתרשים עמודות אופקי |
| **סיכום קטגוריות** | טבלה מקובצת עם סך הוצאה לכל קטגוריה |
| **תובנות וחריגים** | זיהוי עסקאות חריגות וקפיצות בהוצאות |
| **טבלת עסקאות** | כל העסקאות עם חיפוש, מיון וסינון |
| **סינון חודשים** | סינון דינאמי לפי חודש — עובד עם מספר קבצים |

> **פרטיות:** קבצי PDF נשארים אצלך בלבד ולא מועלים לשום מקום.

---

## התקנה

### דרישות מוקדמות

- Python 3.10 ומעלה
- Git

### שלב 1 — שכפול הריפו

```bash
git clone https://github.com/dmarcx/credit-card-dashboard.git
cd credit-card-dashboard
```

### שלב 2 — יצירת סביבה וירטואלית (מומלץ)

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac / Linux
source .venv/bin/activate
```

### שלב 3 — התקנת תלויות

```bash
pip install -r requirements.txt
```

### שלב 4 — הרצה

```bash
streamlit run app.py
```

הדפדפן ייפתח אוטומטית בכתובת `http://localhost:8501`.

---

## שימוש

1. **העלאת PDF** — גרור קובץ פירוט כאל לאזור ההעלאה בסרגל הצד, או לחץ על Browse files. ניתן להעלות **מספר חודשים** בו-זמנית.
2. **סינון חודשים** — לאחר הטעינה, בחר חודשים בסרגל הצד לצפייה ממוקדת.
3. **סינון קטגוריות** — הסתר/הצג קטגוריות ספציפיות.
4. **חיפוש ספק** — בטבלת העסקאות, חפש לפי שם בית עסק.
5. **נתוני הדגמה** — ללא PDF? לחץ על "נתוני הדגמה" לראות את הדשבורד עם נתונים מדומים.

---

## מבנה הפרויקט

```
credit-card-dashboard/
├── app.py            # ממשק משתמש — Streamlit בלבד, ללא לוגיקה עסקית
├── parser.py         # חילוץ נתונים מ-PDF וטיפול בעברית RTL
├── analytics.py      # חישובי KPI, אגרגציות, זיהוי חריגים, נתוני הדגמה
├── requirements.txt  # תלויות Python
└── README.md
```

### זרימת הנתונים

```
PDF קובץ
    ↓
parser.py → parse_pdf()
    ↓ DataFrame: date | merchant | amount | category
analytics.py → compute_kpis() / get_category_breakdown() / get_anomalies()
    ↓ מדדים מחושבים
app.py → Streamlit renders dashboard
```

---

## מחסנית טכנולוגית

| שכבה | טכנולוגיה |
|---|---|
| שפה | Python 3.10+ |
| ממשק משתמש | Streamlit |
| עיבוד נתונים | Pandas |
| חילוץ PDF | pdfplumber |
| ויזואליזציה | Plotly Express |
| גיבוי | GitHub (קוד בלבד, ללא PDF) |

---

## גיבוי אוטומטי

הפרויקט מוגדר עם **Stop hook** של Claude Code שמבצע `git commit` ו-`git push` אוטומטית בסוף כל סשן פיתוח. ר' [`.claude/settings.json`](.claude/settings.json).

קבצי PDF מוחרגים מ-Git לפי [`.gitignore`](.gitignore) — הם לא יועלו לשום מקום.

---

## פתרון בעיות

**הפירוט לא מזוהה**
- ודא שהקובץ הוא פירוט כרטיס **כאל** (ויזה/דיינרס/מאסטרקארד דרך כאל).
- הפורמט הנתמך הוא "דף פירוט דיגיטלי" שנשלח במייל.

**שמות ספקים הפוכים**
- לא אמור לקרות — `parser.py` מטפל בתיקון RTL אוטומטי.
- אם אתה רואה טקסט הפוך, פתח issue עם דוגמה (ללא מידע אישי).

**שגיאת התקנה**
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

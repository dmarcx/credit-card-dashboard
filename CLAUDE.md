# CLAUDE.md — Credit Card Dashboard Project

## Project Objective

Build a web application that allows a user to upload one or more PDF files of credit card statements, automatically extract transaction data (date, merchant, amount, category), and display a smart analytical dashboard with insights and anomaly detection.

---

## Features

### 1. File Upload
- Drag & Drop upload area supporting multiple PDF files simultaneously.
- Files should be parsed on upload and their data merged into a unified dataset.

### 2. Dynamic Month Filter
- When multiple months/files are uploaded, a filter (sidebar or top bar) lets the user select which month(s) to view.
- Default: show all months combined.

### 3. KPI Cards (Top of Dashboard)
- **Total Spend** — sum of all transactions in the selected period.
- **Monthly Average** — average spend per month.
- **Transaction Count** — total number of transactions.

### 4. Interactive Pie Chart
- Displays spending distribution by category using Plotly Express.
- Hoverable slices showing category name, total amount, and percentage.

### 5. Category Summary Table
- Grouped table: Category → Total Spend → Number of Transactions.
- Sortable by amount.

### 6. Top Merchants
- List of the top 5–10 merchants by total spend.
- Displayed as a bar chart or ranked table.

### 7. Insights & Anomalies
- Detect categories or months where spending jumped significantly vs. the previous month (e.g., >50% increase).
- Flag individual transactions that are unusually large (e.g., >2× the category average).
- Display as highlighted cards or an alert-style section.

### 8. Full Transactions Table
- Complete list of all transactions with columns: Date, Merchant, Amount, Category.
- Supports: text search, column sorting, and category/month filtering.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| UI Framework | Streamlit |
| Data Processing | Pandas |
| PDF Extraction | `pdfplumber` (primary), `PyMuPDF` (fallback) |
| Hebrew PDF Support | Claude API (`claude-sonnet-4-6`) for structured extraction when direct parsing fails |
| Visualization | Plotly Express |

---

## Architecture

Keep a strict separation of concerns across three core modules:

```
Credit_Card_Dashboard/
├── app.py            # Streamlit UI — layout, widgets, rendering
├── parser.py         # PDF ingestion & raw text/table extraction
├── analytics.py      # Data transformations, aggregations, anomaly detection
├── requirements.txt  # Python dependencies
└── CLAUDE.md         # This file
```

### `app.py`
- Imports from `parser.py` and `analytics.py`.
- Handles all Streamlit state (`st.session_state`), sidebar filters, and rendering.
- No business logic here — only UI calls.

### `parser.py`
- Responsible for reading PDF files and returning a normalized `pd.DataFrame` with columns: `date`, `merchant`, `amount`, `category`.
- Primary path: `pdfplumber` table extraction.
- Fallback path: send raw text to Claude API with a structured extraction prompt.
- Must handle Hebrew RTL text reversal and UTF-8 encoding issues.

### `analytics.py`
- Receives a clean DataFrame and returns computed metrics.
- Functions for: KPI calculation, category aggregation, top merchants, anomaly detection.
- No I/O or UI logic here.

---

## Development Rules

### Hebrew & RTL Support
- Always check for reversed Hebrew strings from PDF extraction and apply `[::-1]` or `arabic_reshaper` / `bidi` corrections as needed.
- Ensure the Streamlit UI renders Hebrew text correctly (use `st.markdown` with RTL CSS if needed).

### Code Quality
- **Type hints** on all function signatures.
- **Docstrings** on all functions (one-line minimum; full description for complex logic).
- **No magic numbers** — define constants at the top of each module.

### Error Handling
- The app must never crash on an unrecognized PDF. Wrap all parsing in `try/except` and display a user-friendly `st.warning()` message.
- Validate that extracted DataFrames have the required columns before passing them downstream.
- If the Claude API is unavailable, fall back gracefully and inform the user.

### Claude API Usage (parser.py)
- Use model: `claude-sonnet-4-6`
- Prompt should request JSON output with fields: `date`, `merchant`, `amount`, `category`.
- Cache API results in `st.session_state` to avoid redundant calls on re-renders.

---

## Sample PDF
A reference PDF (`דף פירוט דיגיטלי כאל 01-26.pdf`) is included in the project root. Use it as the primary test case during development to validate the parser output.

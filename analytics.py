"""
analytics.py — Data transformations, aggregations, and anomaly detection.

No I/O or UI logic here. All functions receive DataFrames and return
computed metrics. Imported by app.py.
"""

import calendar
import random
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

# ── Constants ────────────────────────────────────────────────────────────────────

CATEGORIES: list[str] = [
    "מזון ומסעדות",
    "סופרמרקט",
    "קניות ואופנה",
    "דלק ותחבורה",
    "בילוי ופנאי",
    "בריאות ורפואה",
    "חשבונות ושירותים",
    "חינוך",
]

MERCHANTS: dict[str, list[str]] = {
    "מזון ומסעדות": ["מקדונלדס", "קפה קפה", "ארומה", "בורגר קינג", "פיצה האט", "שווארמה פינת הרחוב"],
    "סופרמרקט": ["שופרסל", "רמי לוי", "מגה", "ויקטורי", "יוחננוף"],
    "קניות ואופנה": ["זארה", "H&M", "קסטרו", "פוקס", "עדיקה", "רנואר"],
    "דלק ותחבורה": ["פז", "דלק", "סונול", "רב-קו", "גט"],
    "בילוי ופנאי": ["YES", "HOT", "סינמה סיטי", "הוט נט", "גולן טלקום"],
    "בריאות ורפואה": ["סופר-פארם", "ניו-פארם", "מכבי שירותי בריאות", "מאיר פארם"],
    "חשבונות ושירותים": ["חברת החשמל", "מי אביב", "HOT נט", "פרטנר"],
    "חינוך": ["האוניברסיטה הפתוחה", "קורסרה", "גוגל פלי"],
}

AMOUNT_RANGES: dict[str, tuple[float, float]] = {
    "מזון ומסעדות": (30.0, 180.0),
    "סופרמרקט": (80.0, 600.0),
    "קניות ואופנה": (50.0, 500.0),
    "דלק ותחבורה": (100.0, 350.0),
    "בילוי ופנאי": (30.0, 200.0),
    "בריאות ורפואה": (20.0, 300.0),
    "חשבונות ושירותים": (80.0, 400.0),
    "חינוך": (100.0, 800.0),
}

CATEGORY_WEIGHTS: list[int] = [20, 25, 15, 10, 8, 7, 10, 5]

ANOMALY_THRESHOLD_RATIO: float = 2.0   # flag if > 2× category average
SPIKE_THRESHOLD_PCT: float = 0.50      # flag if > 50% MoM increase
MAX_ANOMALIES: int = 6
RECURRING_MIN_MONTHS: int = 2          # min distinct billing months to be "recurring"
ONE_TIME_MIN_AMOUNT: float = 150.0     # min ₪ to flag as notable one-time purchase
MAX_RECURRING: int = 8
MAX_ONE_TIME: int = 6

MOCK_SEED: int = 42
MOCK_BASE_DATE: date = date(2025, 11, 1)
MOCK_NUM_MONTHS: int = 3
MOCK_TRANSACTIONS_RANGE: tuple[int, int] = (40, 60)


# ── Mock Data ────────────────────────────────────────────────────────────────────

def get_mock_data() -> pd.DataFrame:
    """Generate realistic mock credit card transactions across 3 months.

    Returns:
        DataFrame with columns: date (datetime64), merchant (str),
        amount (float), category (str). Sorted by date ascending.
    """
    random.seed(MOCK_SEED)
    np.random.seed(MOCK_SEED)

    rows: list[dict] = []
    base = MOCK_BASE_DATE

    for offset in range(MOCK_NUM_MONTHS):
        year = base.year + (base.month - 1 + offset) // 12
        month = (base.month - 1 + offset) % 12 + 1
        days_in_month = calendar.monthrange(year, month)[1]

        for i in range(random.randint(*MOCK_TRANSACTIONS_RANGE)):
            category = random.choices(CATEGORIES, weights=CATEGORY_WEIGHTS, k=1)[0]
            merchant = random.choice(MERCHANTS[category])
            day = random.randint(1, days_in_month)
            lo, hi = AMOUNT_RANGES[category]
            amount = round(random.uniform(lo, hi), 2)

            # Inject one anomalous transaction in month 2
            if i == 0 and offset == 1:
                amount = round(amount * 4.5, 2)

            rows.append({
                "date": date(year, month, day),
                "merchant": merchant,
                "amount": amount,
                "category": category,
            })

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["billing_month"] = df["date"].dt.to_period("M")
    return df.sort_values("date").reset_index(drop=True)


# ── Analytics ────────────────────────────────────────────────────────────────────

def compute_kpis(df: pd.DataFrame) -> dict[str, Any]:
    """Compute top-level KPIs: total spend, monthly average, transaction count.

    Args:
        df: Transactions DataFrame with 'amount' and 'date' columns.

    Returns:
        Dict with keys: total_spend, monthly_avg, transaction_count, largest_txn.
    """
    total_spend: float = df["amount"].sum()
    n_months: int = df["billing_month"].nunique() if "billing_month" in df.columns else df["date"].dt.to_period("M").nunique()
    monthly_avg: float = total_spend / n_months if n_months > 0 else 0.0
    largest_txn: pd.Series | None = df.loc[df["amount"].idxmax()] if not df.empty else None

    return {
        "total_spend": total_spend,
        "monthly_avg": monthly_avg,
        "transaction_count": len(df),
        "largest_txn": largest_txn,
    }


def get_category_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate total spend and transaction count per category.

    Args:
        df: Transactions DataFrame.

    Returns:
        DataFrame with columns: category, total, count — sorted by total descending.
    """
    return (
        df.groupby("category")
        .agg(total=("amount", "sum"), count=("amount", "count"))
        .reset_index()
        .sort_values("total", ascending=False)
        .reset_index(drop=True)
    )


def get_top_merchants(df: pd.DataFrame, n: int = 8) -> pd.DataFrame:
    """Return the top N merchants by total spend.

    Args:
        df: Transactions DataFrame.
        n: Number of top merchants to return.

    Returns:
        DataFrame with columns: merchant, total, count — top N by total.
    """
    return (
        df.groupby("merchant")
        .agg(total=("amount", "sum"), count=("amount", "count"))
        .reset_index()
        .sort_values("total", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )


def get_insights(df: pd.DataFrame) -> dict[str, list[dict]]:
    """Analyse transactions and return three insight categories.

    Sections:
    - recurring: merchants that appear in ≥ RECURRING_MIN_MONTHS distinct billing months.
    - one_time:  merchants with exactly one transaction, amount ≥ ONE_TIME_MIN_AMOUNT,
                 only relevant when ≥ 2 months of data exist.
    - alerts:    large single transactions (> ANOMALY_THRESHOLD_RATIO × cat avg)
                 and month-over-month category spend spikes.

    Args:
        df: Transactions DataFrame with billing_month column.

    Returns:
        Dict with keys 'recurring', 'one_time', 'alerts' — each a list of dicts.
    """
    result: dict[str, list[dict]] = {"recurring": [], "one_time": [], "alerts": []}

    if df.empty:
        return result

    df2 = df.copy()
    if "billing_month" not in df2.columns:
        df2["billing_month"] = df2["date"].dt.to_period("M")
    n_months: int = df2["billing_month"].nunique()

    # ── Single groupby pass used for both recurring and one-time detection ──
    if n_months >= RECURRING_MIN_MONTHS:
        merch_stats = (
            df2.groupby("merchant")
            .agg(
                n_txn=("amount", "count"),
                months=("billing_month", "nunique"),
                avg=("amount", "mean"),
                total=("amount", "sum"),
                category=("category", lambda x: x.mode().iloc[0]),
            )
            .reset_index()
        )

        rec = (
            merch_stats[merch_stats["months"] >= RECURRING_MIN_MONTHS]
            .sort_values("avg", ascending=False)
            .head(MAX_RECURRING)
        )
        result["recurring"] = rec.to_dict("records")

        ot = (
            merch_stats[
                (merch_stats["n_txn"] == 1)
                & (merch_stats["months"] == 1)
                & (merch_stats["total"] >= ONE_TIME_MIN_AMOUNT)
            ]
            .sort_values("total", ascending=False)
            .head(MAX_ONE_TIME)
            .rename(columns={"total": "amount"})
        )
        result["one_time"] = ot.to_dict("records")

    # ── Alerts: large single transactions ──
    cat_avg = df2.groupby("category")["amount"].mean()
    alerts: list[dict[str, str]] = []
    for _, row in df2.iterrows():
        avg = cat_avg[row["category"]]
        if row["amount"] > avg * ANOMALY_THRESHOLD_RATIO:
            ratio = row["amount"] / avg
            alerts.append({
                "message": (
                    f'עסקה חריגה: {row["merchant"]} — '
                    f'₪{row["amount"]:,.0f} '
                    f'(פי {ratio:.1f} מממוצע הקטגוריה)'
                ),
                "severity": "high",
            })

    # ── Alerts: month-over-month spikes ──
    pivot = df2.groupby(["billing_month", "category"])["amount"].sum().unstack(fill_value=0.0)
    sorted_months = sorted(pivot.index.tolist())
    for i in range(1, len(sorted_months)):
        prev_m, curr_m = sorted_months[i - 1], sorted_months[i]
        for cat in pivot.columns:
            prev_val = pivot.loc[prev_m, cat]
            curr_val = pivot.loc[curr_m, cat]
            if prev_val > 0:
                pct = (curr_val - prev_val) / prev_val
                if pct > SPIKE_THRESHOLD_PCT:
                    alerts.append({
                        "message": (
                            f'קפיצה בקטגוריה "{cat}": '
                            f'+{pct:.0%} לעומת {str(prev_m)}'
                        ),
                        "severity": "medium",
                    })

    result["alerts"] = alerts[:MAX_ANOMALIES]
    return result


def get_anomalies(df: pd.DataFrame) -> list[dict[str, str]]:
    """Backward-compatible wrapper — returns the alerts list from get_insights."""
    return get_insights(df)["alerts"]

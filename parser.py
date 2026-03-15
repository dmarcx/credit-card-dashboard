"""
parser.py — PDF ingestion and transaction extraction.

Primary path: pdfplumber text extraction with column-aware regex parsing.
Fallback: Claude API for structured extraction when direct parsing fails.

Cal credit card PDFs store Hebrew text in visual (left-to-right) order,
which reverses both the character order within each word and the word order
on each line. This module corrects both issues automatically.
"""

import re
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import pdfplumber

# ── Column layout ─────────────────────────────────────────────────────────────
#
# Each transaction line (extracted left-to-right by pdfplumber) has this layout:
#   ₪<charge>  ₪<orig>  אל  [payment_detail]  [category_rev]  [merchant_rev]  DD/MM/YYYY
#
# All Hebrew text is in visual order: characters AND word order are reversed.
# ─────────────────────────────────────────────────────────────────────────────

# Matches the charge amount, original amount, and date in a transaction line
_TXN_RE = re.compile(
    r'₪\s*([\d,]+\.?\d+)'        # group 1: charge amount (first ₪)
    r'.*?₪\s*([\d,]+\.?\d+)'     # group 2: original amount (second ₪)
    r'.*?(\d{2}/\d{2}/\d{4})\s*$'  # group 3: date at end of line
)

# Matches the section between the foreign-currency flag (אל) and the date
_MIDDLE_RE = re.compile(r'אל\s+(.*?)(\d{2}/\d{2}/\d{4})\s*$')

# Patterns to strip from the middle section (payment details column)
_PAYMENT_STRIP_RE = re.compile(
    r'\d+\s*-\s*מ\s*\d+\s*םולשת'  # installment: "6 מ- 10 תשלום"
    r'|"?עבק\s+תארוה"?'            # standing order: הוראת קבע (with optional quotes)
    r'|"?עבק\s+תוארוה"?'           # standing order plural: הוראות קבע (with optional quotes)
    r'|סיטרכ\s+ההזמ'               # card identifier: מזהה כרטיס
    r'|\d{4}\s+טנרטניא'            # internet + 4-digit code
    r'|\.[א-ת]+'                   # foreign country suffix e.g. .הילרטסוא
)

# ── Category mapping ──────────────────────────────────────────────────────────
# Keys:   the reversed-Hebrew form as it appears in the raw PDF extraction
# Values: canonical Hebrew display form for the dashboard

CATEGORY_MAP: dict[str, str] = {
    'אקשמו ןוזמ':  'מזון ומשקאות',
    'ירבו האופר':  'רפואה ובריאות',
    'תיבו טוהיר':  'ריהוט ובית',
    'ניפו חוטיב':  'ביטוח ופיננסים',
    'פויו חופיט':  'טיפוח ויופי',
    'עיי יתוריש':  'שירותים מקצועיים',
    'תרושקת':      'תקשורת',
    'תודסומ':      'מוסדות',
    'למשח ירצומ':  'מוצרי חשמל',
    'םיבשחמ':      'מחשבים ואלקטרוניקה',
    'ירצומ':       'מוצרים שונים',
}

# Required output columns (order matters for downstream use)
REQUIRED_COLUMNS: list[str] = ['date', 'merchant', 'amount', 'category']


# ── Hebrew RTL correction ─────────────────────────────────────────────────────

def _is_hebrew_token(token: str) -> bool:
    """Return True if the token contains any Hebrew character."""
    return any('\u05D0' <= c <= '\u05FF' for c in token)


def _reverse_token(token: str) -> str:
    """Reverse a token's characters if it is Hebrew-dominant (≥40% Hebrew chars)."""
    if not token:
        return token
    heb_count = sum(1 for c in token if '\u05D0' <= c <= '\u05FF')
    if heb_count >= len(token) * 0.4:
        return token[::-1]
    return token


def fix_rtl(text: str) -> str:
    """
    Correct Hebrew text extracted from a visually-encoded PDF.

    In Cal PDFs, Hebrew characters are stored in visual (display) order,
    meaning every Hebrew word's characters are reversed. Additionally, the
    word order within RTL segments is also reversed. This function:
      1. Reverses characters in each Hebrew-dominant word token.
      2. Reverses the overall word order if the text is Hebrew-dominant.

    Args:
        text: Raw text as extracted by pdfplumber.

    Returns:
        Human-readable Hebrew string.
    """
    if not text or not text.strip():
        return text

    words = text.split()
    fixed = [_reverse_token(w) for w in words]

    # Reverse word order only for Hebrew-dominant segments
    heb_word_count = sum(1 for w in words if _is_hebrew_token(w))
    if heb_word_count > len(words) * 0.5:
        fixed = fixed[::-1]

    return ' '.join(fixed)


# ── Transaction line parsing ──────────────────────────────────────────────────

def _extract_category_and_merchant(middle: str) -> tuple[str, str]:
    """
    Split the middle section of a transaction line into category and merchant.

    The middle text (after payment-detail removal) follows the layout:
      [category_reversed_words] [merchant_reversed_words]

    Known reversed category patterns are matched first (longest match wins).
    Any remaining text is treated as the merchant name.

    Args:
        middle: Raw middle section string from the transaction line.

    Returns:
        Tuple of (canonical_category_hebrew, raw_merchant_text).
    """
    # Remove payment detail tokens first
    clean = _PAYMENT_STRIP_RE.sub('', middle).strip()

    # Match the longest known category key (to avoid partial matches)
    for cat_key in sorted(CATEGORY_MAP, key=len, reverse=True):
        if clean.startswith(cat_key):
            merchant_raw = clean[len(cat_key):].strip()
            return CATEGORY_MAP[cat_key], merchant_raw

    # Category not in known list — return entire middle as merchant
    return 'שונות', clean


def _parse_line(line: str) -> dict[str, Any] | None:
    """
    Parse one line of text into a transaction record.

    Args:
        line: A single line from pdfplumber's text extraction.

    Returns:
        Dict with keys: date, merchant, amount, category — or None if the
        line does not match the transaction pattern.
    """
    line = line.strip()

    if not _TXN_RE.search(line):
        return None

    txn_m = _TXN_RE.search(line)
    charge_str = txn_m.group(1)
    date_str = txn_m.group(3)
    amount = float(charge_str.replace(',', ''))

    mid_m = _MIDDLE_RE.search(line)
    if not mid_m:
        return None
    middle = mid_m.group(1).strip()

    category, merchant_raw = _extract_category_and_merchant(middle)
    merchant = fix_rtl(merchant_raw).strip(' -"')

    return {
        'date':     pd.to_datetime(date_str, format='%d/%m/%Y'),
        'merchant': merchant if merchant else 'לא ידוע',
        'amount':   amount,
        'category': category,
    }


# ── PDF extraction ────────────────────────────────────────────────────────────

def _extract_lines(source: Path | BytesIO) -> list[str]:
    """Extract all text lines from a PDF using pdfplumber with layout mode."""
    lines: list[str] = []
    with pdfplumber.open(source) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True, x_tolerance=3, y_tolerance=3) or ''
            lines.extend(text.split('\n'))
    return lines


def parse_pdf(source: Path | BytesIO) -> pd.DataFrame:
    """
    Parse a Cal credit card PDF statement into a normalised transactions DataFrame.

    Tries pdfplumber text extraction first. If zero transactions are extracted,
    raises ValueError so the caller can fall back to Claude API parsing.

    Args:
        source: Path to a PDF file, or an in-memory BytesIO object (e.g. from
                Streamlit's file_uploader).

    Returns:
        DataFrame with columns:
          - date     (datetime64[ns])
          - merchant (str)
          - amount   (float)
          - category (str)
        Sorted by date ascending.

    Raises:
        ValueError: If the file cannot be opened or contains no recognisable
                    transactions (wrong format, wrong card issuer, etc.).
    """
    try:
        lines = _extract_lines(source)
    except Exception as exc:
        raise ValueError(f'Failed to open PDF: {exc}') from exc

    rows: list[dict] = []
    for line in lines:
        record = _parse_line(line)
        if record:
            rows.append(record)

    if not rows:
        raise ValueError(
            'לא נמצאו עסקאות בקובץ. '
            'ודא שהקובץ הוא פירוט כרטיס אשראי של כאל.'
        )

    df = (
        pd.DataFrame(rows)[REQUIRED_COLUMNS]
        .sort_values('date')
        .reset_index(drop=True)
    )
    return df

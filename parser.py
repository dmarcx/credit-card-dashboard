"""
parser.py — PDF ingestion and transaction extraction.

Parsing paths (tried in order):
  1. Cal card regex parser  — pdfplumber + column-aware regex (₪-anchored lines).
  2. Isracard regex parser  — section-aware regex for ישראכרט PDF format.
  3. Claude API fallback    — sends raw text to claude-sonnet-4-6 for JSON extraction.

Both Cal and Isracard PDFs store Hebrew text in visual (left-to-right) order,
which reverses both the character order within each word and the word order
on each line. The fix_rtl() helper corrects both issues.
"""

import json
import os
import re
from io import BytesIO
from pathlib import Path
from typing import Any

import anthropic
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

# ── Isracard constants ─────────────────────────────────────────────────────────
#
# Isracard PDFs are split into two sections:
#   Section A: ל"וחב תושיכר  — foreign-currency purchases
#   Section B: ץראב - וכוז / וביוחש תוקסע — local (Israel) purchases
#
# Local line layout (left-to-right as extracted):
#   [N ךותמ M םולשת]  CHARGE  ORIGINAL  CATEGORY_REV  MERCHANT_REV  [CARD_TYPE]  DD/MM/YY
#
# Foreign line layouts:
#   NIS-billed:  CHARGE ₪ CHARGE  MERCHANT  TYPE_CODE  DD/MM/YY
#   USD-billed:  CHARGE  FEE  RATE  CONV_DATE  USD_AMT $  MERCHANT  TYPE_CODE  DD/MM/YY
# ──────────────────────────────────────────────────────────────────────────────

# Reversed Hebrew → canonical category (Isracard local section)
_IC_CATEGORY_MAP: dict[str, str] = {
    'תונוש':        'שונות',
    'טרופס/יאנפ':  'בילוי ופנאי',
    'המראפ':        'בריאות ורפואה',
    'רפוס/תלוכמ':  'סופרמרקט',
    'הפק/תודעסמ':  'מזון ומסעדות',
    'תרושקת':       'תקשורת',
    'קלד':          'דלק ותחבורה',
    'בכר יתוריש':  'דלק ותחבורה',
    'יאופר תורש':  'בריאות ורפואה',
    'תיב ילכ':     'ריהוט ובית',
    'השבלה':        'קניות ואופנה',
}

# Card-type / payment-mode tokens to strip from the middle section
_IC_STRIP_RE = re.compile(
    r'דיינ\.שת'    # digital payment (תשלום דיגיטלי reversed)
    r'|עבק\.ה'     # standing order (הוראת קבע reversed)
    r'|גצוה אל'    # "not displayed" (לא הוצג reversed)
)

# Local Isracard transaction line (re.search — handles installment prefix & promo text)
# Captures: group 1=charge, group 2=original, group 3=middle, group 4=date
_IC_LOCAL_RE = re.compile(
    r'([\d,]+\.\d+)'                         # group 1: charge amount
    r'\s+([\d,]+\.\d+)'                      # group 2: original amount
    r'\s+(.+)'                               # group 3: middle (category + merchant + card type)
    r'\s+(\d{2}/\d{2}/\d{2,4})\s*$'         # group 4: date
)

# Foreign NIS-billed: "105.00 ₪ 105.00 A DOBE.COM א 19/12/25"
_IC_FOR_NIS_RE = re.compile(
    r'^(-?[\d,]+\.\d+)'                      # group 1: charge NIS (possibly negative = refund)
    r'\s+₪\s+[-\d,]+\.\d+'                  # ₪ original NIS (skip)
    r'\s+(.+?)'                              # group 2: merchant name
    r'\s+[א-ת]'                             # single Hebrew type code
    r'\s+(\d{2}/\d{2}/\d{2,4})\s*$'         # group 3: date
)

# Foreign USD-billed: "19.46 0.28 3.2020 12/12/25 5.99 $ L INGOCHAMPION.COM א 12/12/25"
_IC_FOR_USD_RE = re.compile(
    r'^([\d,]+\.\d+)'                        # group 1: charge NIS
    r'\s+[\d,]+\.\d+'                        # fee (skip)
    r'\s+[\d.]+\s+'                          # exchange rate (skip)
    r'\d{2}/\d{2}/\d{2,4}\s+'               # conversion date (skip)
    r'[\d,]+\.\d+\s+\$\s+'                  # USD amount + $ (skip)
    r'(.+?)'                                 # group 2: merchant name
    r'\s+[א-ת]'                             # single Hebrew type code
    r'\s+(\d{2}/\d{2}/\d{2,4})\s*$'         # group 3: date
)


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


# ── Isracard parsing ──────────────────────────────────────────────────────────

def _ic_extract_category_and_merchant(middle: str) -> tuple[str, str]:
    """
    Split an Isracard local-section middle string into category and merchant.

    Strips payment-mode tokens first, then matches the longest known reversed
    category prefix. Remainder is the raw (reversed) merchant name.
    """
    clean = _IC_STRIP_RE.sub('', middle).strip()
    for cat_key in sorted(_IC_CATEGORY_MAP, key=len, reverse=True):
        if clean.startswith(cat_key):
            merchant_raw = clean[len(cat_key):].strip()
            return _IC_CATEGORY_MAP[cat_key], merchant_raw
    return 'שונות', clean


def _fix_latin_merchant(name: str) -> str:
    """
    Remove pdfplumber's space artifact in Latin merchant names.

    pdfplumber sometimes separates the first character from the rest:
    "A DOBE.COM" → "ADOBE.COM", "G OOGLE ONE" → "GOOGLE ONE".
    """
    return re.sub(r'^([A-Z]) ([A-Z])', r'\1\2', name.strip())


def _parse_date_isracard(date_str: str) -> pd.Timestamp:
    """Parse a DD/MM/YY or DD/MM/YYYY date string from an Isracard PDF."""
    fmt = '%d/%m/%y' if len(date_str) == 8 else '%d/%m/%Y'
    return pd.to_datetime(date_str, format=fmt)


def _detect_isracard(lines: list[str]) -> bool:
    """Return True if the extracted lines appear to be an Isracard statement."""
    for line in lines[:60]:
        if 'ל"וחב תושיכר' in line or ('ץראב' in line and 'וכוז' in line):
            return True
    return False


def _parse_isracard_from_lines(lines: list[str]) -> pd.DataFrame:
    """
    Parse Isracard statement lines into a normalised transactions DataFrame.

    Processes two sections:
      - Foreign (ל"וחב תושיכר): Latin merchant names, NIS or USD billed.
      - Local  (ץראב ...):      Hebrew merchant/category in reversed visual order.

    Args:
        lines: Text lines from pdfplumber extraction.

    Returns:
        DataFrame with columns: date, merchant, amount, category.

    Raises:
        ValueError: If no valid transactions are found.
    """
    rows: list[dict] = []
    section: str | None = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # ── Section detection ──
        if 'ל"וחב תושיכר' in line:
            section = 'foreign'
            continue
        if 'ץראב' in line and 'וכוז' in line:
            section = 'local'
            continue
        # ── Total / summary lines — skip ──
        if 'כ"הס' in line or 'מ"עמ' in line:
            continue

        # ── Local transactions ──
        if section == 'local':
            m = _IC_LOCAL_RE.search(line)
            if not m:
                continue
            charge_str, middle, date_str = m.group(1), m.group(3), m.group(4)
            amount = float(charge_str.replace(',', ''))
            if amount <= 0:
                continue
            category, merchant_raw = _ic_extract_category_and_merchant(middle)
            merchant = fix_rtl(merchant_raw).strip(' -"\'')
            # Override category for cash withdrawals
            if 'משיכת מזומנים' in merchant:
                category = 'משיכת מזומנים'
            rows.append({
                'date':     _parse_date_isracard(date_str),
                'merchant': merchant or 'לא ידוע',
                'amount':   amount,
                'category': category,
            })

        # ── Foreign transactions ──
        elif section == 'foreign':
            m = _IC_FOR_NIS_RE.match(line) or _IC_FOR_USD_RE.match(line)
            if not m:
                continue
            charge_str, merchant_raw, date_str = m.group(1), m.group(2), m.group(3)
            amount = float(charge_str.replace(',', ''))
            if amount <= 0:
                continue
            rows.append({
                'date':     _parse_date_isracard(date_str),
                'merchant': _fix_latin_merchant(merchant_raw),
                'amount':   amount,
                'category': 'רכישות חו"ל',
            })

    if not rows:
        raise ValueError('לא נמצאו עסקאות בקובץ הישראכרט.')

    return (
        pd.DataFrame(rows)[REQUIRED_COLUMNS]
        .sort_values('date')
        .reset_index(drop=True)
    )


# ── PDF extraction ────────────────────────────────────────────────────────────

def _extract_lines(source: Path | BytesIO) -> list[str]:
    """Extract all text lines from a PDF using pdfplumber with layout mode."""
    lines: list[str] = []
    with pdfplumber.open(source) as pdf:
        for page in pdf.pages:
            text = page.extract_text(layout=True, x_tolerance=3, y_tolerance=3) or ''
            lines.extend(text.split('\n'))
    return lines


def _extract_full_text(source: Path | BytesIO) -> str:
    """Extract all text from a PDF as a single string (for Claude API fallback)."""
    parts: list[str] = []
    # Reset buffer position if BytesIO was already read
    if isinstance(source, BytesIO):
        source.seek(0)
    with pdfplumber.open(source) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ''
            if text.strip():
                parts.append(text)
    return '\n'.join(parts)


_CLAUDE_EXTRACTION_PROMPT = """\
להלן טקסט גולמי שחולץ מקובץ PDF של פירוט כרטיס אשראי (ישראכרט, כאל, ויזה, או אחר).
חלץ את כל העסקאות מהטקסט והחזר JSON בלבד — מערך של אובייקטים, כל אחד עם השדות:
  "date"     — תאריך בפורמט DD/MM/YYYY
  "merchant" — שם בית העסק בעברית
  "amount"   — סכום החיוב כמספר עשרוני (חיובי)
  "category" — קטגוריה בעברית, אחת מ: מזון ומשקאות, סופרמרקט, קניות ואופנה,
               דלק ותחבורה, בילוי ופנאי, בריאות ורפואה, תקשורת, ריהוט ובית,
               מוצרי חשמל, ביטוח ופיננסים, טיפוח ויופי, שונות

כללים:
- כלול רק חיובים ממשיים (לא עמלות, לא הפניות לדפים אחרים).
- אם הסכום מופיע בשקלים — השתמש בו ישירות.
- אם שם העסק מופיע הפוך (ויזואלית) — תקן אותו לקריא.
- החזר JSON בלבד, ללא טקסט נוסף.

טקסט ה-PDF:
"""


def _parse_via_claude(source: Path | BytesIO) -> pd.DataFrame:
    """
    Fallback: use Claude API to extract transactions from unrecognised PDF formats.

    Args:
        source: Path or BytesIO of the PDF file.

    Returns:
        Normalised transactions DataFrame.

    Raises:
        ValueError: If the API key is missing, or Claude returns no valid transactions.
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get('ANTHROPIC_API_KEY')
        except Exception:
            pass
    if not api_key:
        raise ValueError(
            'לא נמצא מפתח ANTHROPIC_API_KEY. '
            'הגדר אותו ב-.streamlit/secrets.toml או כמשתנה סביבתי.'
        )

    raw_text = _extract_full_text(source)
    if not raw_text.strip():
        raise ValueError('לא ניתן לחלץ טקסט מהקובץ.')

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=4096,
        messages=[{'role': 'user', 'content': _CLAUDE_EXTRACTION_PROMPT + raw_text}],
    )

    response_text = message.content[0].text.strip()
    # Strip markdown code fences if present
    if response_text.startswith('```'):
        response_text = re.sub(r'^```[a-z]*\n?', '', response_text)
        response_text = re.sub(r'\n?```$', '', response_text)

    try:
        records = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f'Claude החזיר תגובה לא תקינה: {exc}') from exc

    if not records:
        raise ValueError('Claude לא הצליח לחלץ עסקאות מהקובץ.')

    rows: list[dict] = []
    for rec in records:
        try:
            rows.append({
                'date':     pd.to_datetime(rec['date'], format='%d/%m/%Y'),
                'merchant': str(rec.get('merchant', 'לא ידוע')).strip(),
                'amount':   float(rec['amount']),
                'category': str(rec.get('category', 'שונות')).strip(),
            })
        except (KeyError, ValueError):
            continue  # skip malformed records

    if not rows:
        raise ValueError('לא נמצאו עסקאות תקינות בתגובת Claude.')

    return (
        pd.DataFrame(rows)[REQUIRED_COLUMNS]
        .sort_values('date')
        .reset_index(drop=True)
    )


def parse_pdf(source: Path | BytesIO) -> pd.DataFrame:
    """
    Parse a credit card PDF statement into a normalised transactions DataFrame.

    Tries pdfplumber + regex parsing first (optimised for Cal card format).
    If zero transactions are found, falls back to Claude API extraction,
    which supports Isracard, Visa, and other Hebrew card formats.

    Args:
        source: Path to a PDF file, or an in-memory BytesIO object.

    Returns:
        DataFrame with columns: date, merchant, amount, category.

    Raises:
        ValueError: If parsing fails via both methods.
    """
    try:
        lines = _extract_lines(source)
    except Exception as exc:
        raise ValueError(f'Failed to open PDF: {exc}') from exc

    # ── Path 2: Isracard regex parser ──
    if _detect_isracard(lines):
        return _parse_isracard_from_lines(lines)

    # ── Path 1: Cal card regex parser ──
    rows: list[dict] = []
    for line in lines:
        record = _parse_line(line)
        if record:
            rows.append(record)

    if rows:
        return (
            pd.DataFrame(rows)[REQUIRED_COLUMNS]
            .sort_values('date')
            .reset_index(drop=True)
        )

    # ── Path 3: Claude API fallback ──
    return _parse_via_claude(source)

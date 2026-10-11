#!/usr/bin/env python3
"""
generate_qr_bills.py
---------------------
Batch-processes a Rashi Heights maintenance-bill PDF (one page per flat/shop)
and stamps a UPI payment QR onto every bill, then saves each bill as its own
PDF file.

Folder layout expected (this script lives at the project root):

    project_root/
        generate_qr_bills.py         <- this file
        flat_shop_preferences.csv    <- FlatNo, QrCodeAmount ("PREFILLED" / "CUSTOM_AMOUNT")
        config.json                  <- optional overrides for QR caption text etc.
        input/                       <- put the source bill PDF(s) here
        output/
            <yyyymmdd_hhmmss>/       <- created fresh on every run

flat_shop_preferences.csv rules
--------------------------------
- QrCodeAmount = PREFILLED -> QR includes the bill's Grand Total as the
  amount (payer just confirms and pays).
- QrCodeAmount = CUSTOM_AMOUNT -> QR omits the amount field entirely (payer
  types the amount in themselves when scanning) -- this matches how a
  generic/static personal UPI QR behaves (no amount baked in).
- QrCodeAmount = BOTH      -> two QRs on the bill: the full-amount (PREFILLED)
  QR at the usual bottom-right position, and the custom-amount (CUSTOM_AMOUNT) QR in
  the blank box at the top right.
- A flat/shop not listed in flat_shop_preferences.csv defaults to PREFILLED.

Run via linux/generate.sh or windows/generate.bat (after running the
matching setup script once), or directly:

    python generate_qr_bills.py
"""

import csv
import datetime
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

import pdfplumber
import qrcode
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
APP_CONFIG_PATH = BASE_DIR / "config.json"

# Defaults used if config.json is missing or a key isn't present in it.
DEFAULT_APP_CONFIG = {
    "input_dir": "input",
    "output_dir": "output",
    "preferences_file": "flat_shop_preferences.csv",
    "payee_upi_id": "yourname@upi",
    "payee_default_name": "YOUR NAME",  # None/empty -> read society name from the bill itself
    # Merchant-QR fields (leave "" to omit -- only needed for bank-issued
    # merchant UPI QR codes, not plain personal VPAs).
    "upi_ver": "",
    "upi_mode": "",
    "upi_orgid": "",
    "upi_mc": "",
    "upi_mid": "",
    "upi_mtid": "",
    "upi_qr_medium": "",
    "caption_prefilled": "Scan to Pay Full Amount\nRs.{amount}",
    "caption_custom": "Scan to Pay Custom Amount",
    # BOTH mode: custom-amount QR in the top-right box (two short caption lines).
    "caption_both_top": ["Pay Custom", "Amount"],
    # Additional: text appended to the UPI remarks (e.g. "A-101 Q1 2025-26 Maintenance").
    "remarks_suffix": "Maintenance",
}


def load_app_config(path):
    """Returns DEFAULT_APP_CONFIG merged with overrides from config.json (if present)."""
    config = dict(DEFAULT_APP_CONFIG)
    if not path.exists():
        return config
    with open(path, encoding='utf-8-sig') as f:
        overrides = json.load(f)
    config.update(overrides)
    return config


APP_CONFIG = load_app_config(APP_CONFIG_PATH)

INPUT_DIR = BASE_DIR / APP_CONFIG["input_dir"]
OUTPUT_ROOT = BASE_DIR / APP_CONFIG["output_dir"]
PREFERENCES_PATH = BASE_DIR / APP_CONFIG["preferences_file"]

PAYEE_UPI_ID = APP_CONFIG["payee_upi_id"]
PAYEE_DEFAULT_NAME = APP_CONFIG["payee_default_name"]
UPI_VER = APP_CONFIG["upi_ver"]
UPI_MODE = APP_CONFIG["upi_mode"]
UPI_ORGID = APP_CONFIG["upi_orgid"]
UPI_MC = APP_CONFIG["upi_mc"]
UPI_MID = APP_CONFIG["upi_mid"]
UPI_MTID = APP_CONFIG["upi_mtid"]
UPI_QR_MEDIUM = APP_CONFIG["upi_qr_medium"]
CAPTION_PREFILLED = APP_CONFIG["caption_prefilled"]
CAPTION_CUSTOM = APP_CONFIG["caption_custom"]
CAPTION_BOTH_TOP = APP_CONFIG["caption_both_top"]
REMARKS_SUFFIX = APP_CONFIG["remarks_suffix"]

MONTHS = {m: i + 1 for i, m in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
     'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
)}

# Blank-zone coordinates (PDF points, top-left origin) -- clear of all text,
# rects, and curves on the Rashi Heights / SocietyMaxx bill template, with
# margin on every side so the QR block reads as its own element.
QR_X0, QR_X1 = 484, 544          # 60pt wide
QR_TOP0, QR_TOP1 = 540, 600      # 60pt tall
CAPTION_CENTER_X = (QR_X0 + QR_X1) / 2
CAPTION_BASELINE_TOP = 609        # ~9pt under the QR
CAPTION_LINE_HEIGHT = 8

# BOTH mode: blank box at the top right of the bill (x 515-570, y 118-183).
TOP_QR_X0, TOP_QR_X1 = 517, 571   # 54pt wide
TOP_QR_TOP0, TOP_QR_TOP1 = 114, 168
TOP_CAPTION_CENTER_X = (TOP_QR_X0 + TOP_QR_X1) / 2
TOP_CAPTION_BASELINES_TOP = (176, 183)


# --------------------------------------------------------------------------
# Flat/shop preferences CSV
# --------------------------------------------------------------------------
def load_preferences(path):
    """Returns dict: normalized flat/shop key -> 'PREFILLED', 'CUSTOM_AMOUNT' or 'BOTH'."""
    config = {}
    if not path.exists():
        print(f"[warn] {path.name} not found -- every bill will default to PREFILLED.")
        return config

    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            flat = (row.get('FlatNo') or '').strip()
            mode = (row.get('QrCodeAmount') or '').strip().upper()
            if not flat:
                continue
            if mode == 'NONE':  # legacy name
                mode = 'CUSTOM_AMOUNT'
            if mode not in ('PREFILLED', 'CUSTOM_AMOUNT', 'BOTH'):
                mode = 'PREFILLED'
            config[normalize_key(flat)] = mode
    return config


def normalize_key(flat_no):
    return re.sub(r'\s+', ' ', flat_no.strip()).upper()


# --------------------------------------------------------------------------
# Bill field extraction (per page)
# --------------------------------------------------------------------------
def extract_fields(page_text):
    if not page_text:
        raise ValueError("Empty page text (is this a scanned/image-only PDF?).")

    society_name = page_text.strip().splitlines()[0].strip().rstrip('.')

    flat_no = None
    for line in page_text.splitlines():
        stripped = line.strip()
        if stripped.startswith('Flat No.'):
            flat_no = stripped.split('Flat No.', 1)[1].strip()
            break
    if not flat_no:
        raise ValueError('Could not find a "Flat No." line on this page.')

    m_total = re.search(r'Grand Total\s*:\s*([\d,]+\.\d{2})', page_text)
    if not m_total:
        raise ValueError('Could not find a "Grand Total :" line on this page.')
    amount = m_total.group(1).replace(',', '')

    m_period = re.search(
        r'Bill for the Period\s+([A-Za-z]+)-(\d{4})\s+to\s+([A-Za-z]+)-(\d{4})',
        page_text
    )
    if not m_period:
        raise ValueError('Could not find a "Bill for the Period ..." line on this page.')
    start_mon, start_year, _end_mon, _end_year = m_period.groups()

    start_month_num = MONTHS[start_mon]
    start_year_num = int(start_year)

    if start_month_num in (4, 5, 6):
        quarter = 1
    elif start_month_num in (7, 8, 9):
        quarter = 2
    elif start_month_num in (10, 11, 12):
        quarter = 3
    else:
        quarter = 4

    if start_month_num >= 4:
        fy_start, fy_end = start_year_num, start_year_num + 1
    else:
        fy_start, fy_end = start_year_num - 1, start_year_num

    return {
        'society_name': society_name,
        'flat_no': flat_no,
        'amount': amount,
        'quarter': quarter,
        'fy_start': fy_start,
        'fy_end': fy_end,
    }


# --------------------------------------------------------------------------
# UPI / QR building
# --------------------------------------------------------------------------
def build_upi_uri(payee_vpa, payee_name, remarks, amount=None,
                   ver=None, mode=None, orgid=None, mc=None, mid=None,
                   mtid=None, qr_medium=None):
    """Builds a upi://pay URI. The merchant-QR fields (ver/mode/orgid/mc/
    mid/mtid/qr_medium) are only included when non-empty, so this also works
    for a plain personal VPA with none of them set."""
    params = []
    if ver:
        params.append(f"ver={quote(ver)}")
    if mode:
        params.append(f"mode={quote(mode)}")
    if orgid:
        params.append(f"orgid={quote(orgid)}")
    params.append(f"pa={quote(payee_vpa, safe='@')}")
    params.append(f"pn={quote(payee_name)}")
    if mc:
        params.append(f"mc={quote(mc)}")
    if mid:
        params.append(f"mid={quote(mid)}")
    if mtid:
        params.append(f"mtid={quote(mtid)}")
    if qr_medium:
        params.append(f"qrMedium={quote(qr_medium)}")
    if amount is not None:
        params.append(f"am={quote(amount)}")
    params.append("cu=INR")
    params.append(f"tn={quote(remarks)}")
    return "upi://pay?" + "&".join(params)


def make_qr_image_bytes(data):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def build_overlay(page_width, page_height, qr_png_bytes, caption, top_qr=None):
    """top_qr (BOTH mode): optional (png_bytes, caption_lines) for the top-right box."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))

    qr_reader = ImageReader(qr_png_bytes)
    qr_w = QR_X1 - QR_X0
    qr_h = QR_TOP1 - QR_TOP0
    c.drawImage(
        qr_reader,
        QR_X0, page_height - QR_TOP1,
        width=qr_w, height=qr_h,
        mask='auto',
    )

    c.setFont("Helvetica-Bold", 7)
    for n, line in enumerate(caption.split("\n")):   # "\n" in a caption = new line
        c.drawCentredString(
            CAPTION_CENTER_X,
            page_height - (CAPTION_BASELINE_TOP + n * CAPTION_LINE_HEIGHT),
            line,
        )

    if top_qr is not None:
        top_png, top_lines = top_qr
        c.drawImage(
            ImageReader(top_png),
            TOP_QR_X0, page_height - TOP_QR_TOP1,
            width=TOP_QR_X1 - TOP_QR_X0, height=TOP_QR_TOP1 - TOP_QR_TOP0,
            mask='auto',
        )
        c.setFont("Helvetica-Bold", 6)
        for line, baseline in zip(top_lines, TOP_CAPTION_BASELINES_TOP):
            c.drawCentredString(
                TOP_CAPTION_CENTER_X, page_height - baseline, line
            )

    c.save()
    buf.seek(0)
    return buf


# --------------------------------------------------------------------------
# Filename helpers
# --------------------------------------------------------------------------
def sanitize_for_filename(text):
    text = re.sub(r'\s+', '_', text.strip())
    text = re.sub(r'[^A-Za-z0-9_\-]', '', text)
    return text


def unique_path(path):
    """If path already exists, append _2, _3, ... before the extension."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    if not INPUT_DIR.exists():
        sys.exit(f"Input folder not found: {INPUT_DIR}\nCreate it and place the bill PDF(s) inside.")

    pdf_paths = sorted(INPUT_DIR.glob("*.pdf"))
    if not pdf_paths:
        sys.exit(f"No PDF files found in {INPUT_DIR}")

    preferences = load_preferences(PREFERENCES_PATH)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_ROOT / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    total_bills = 0
    total_prefilled = 0
    total_custom = 0
    total_both = 0
    errors = []

    for pdf_path in pdf_paths:
        print(f"\nProcessing {pdf_path.name} ...")

        with pdfplumber.open(pdf_path) as plumber_pdf:
            page_texts = [p.extract_text() for p in plumber_pdf.pages]
            page_dims = [(p.width, p.height) for p in plumber_pdf.pages]

        base_reader = PdfReader(str(pdf_path))

        for i, page_text in enumerate(page_texts):
            try:
                fields = extract_fields(page_text)
            except ValueError as e:
                errors.append(f"{pdf_path.name} page {i + 1}: {e}")
                print(f"  [skip] page {i + 1}: {e}")
                continue

            flat_no = fields['flat_no']
            key = normalize_key(flat_no)
            mode = preferences.get(key, 'PREFILLED')

            remarks = (
                f"{flat_no} Q{fields['quarter']} "
                f"{fields['fy_start']}-{fields['fy_end']} {REMARKS_SUFFIX}"
            )
            payee_name = PAYEE_DEFAULT_NAME or fields['society_name']

            def uri_for(amount):
                return build_upi_uri(
                    PAYEE_UPI_ID, payee_name, remarks, amount=amount,
                    ver=UPI_VER, mode=UPI_MODE, orgid=UPI_ORGID,
                    mc=UPI_MC, mid=UPI_MID, mtid=UPI_MTID, qr_medium=UPI_QR_MEDIUM,
                )

            top_qr = None
            if mode == 'PREFILLED':
                upi_uri = uri_for(fields['amount'])
                caption = CAPTION_PREFILLED.format(amount=fields['amount'])
                total_prefilled += 1
            elif mode == 'CUSTOM_AMOUNT':
                upi_uri = uri_for(None)
                caption = CAPTION_CUSTOM
                total_custom += 1
            else:
                # BOTH: full-amount QR at the usual bottom-right spot,
                # custom-amount QR in the top-right box.
                upi_uri = uri_for(fields['amount'])
                caption = CAPTION_PREFILLED.format(amount=fields['amount'])
                top_qr = (
                    make_qr_image_bytes(uri_for(None)),
                    [ln.format(amount=fields['amount']) for ln in CAPTION_BOTH_TOP],
                )
                total_both += 1

            qr_bytes = make_qr_image_bytes(upi_uri)
            page_w, page_h = page_dims[i]
            overlay_buf = build_overlay(page_w, page_h, qr_bytes, caption, top_qr)
            overlay_reader = PdfReader(overlay_buf)

            page_obj = base_reader.pages[i]
            page_obj.merge_page(overlay_reader.pages[0])

            writer = PdfWriter()
            writer.add_page(page_obj)

            out_name = (
                f"{sanitize_for_filename(flat_no)}_"
                f"Q{fields['quarter']}_"
                f"{fields['fy_start']}-{fields['fy_end']}_"
                f"Rashi_Heights_maintenance_bill.pdf"
            )
            out_path = unique_path(out_dir / out_name)

            with open(out_path, "wb") as f:
                writer.write(f)

            total_bills += 1
            print(f"  [{mode:>13}] Flat {flat_no:<8} -> {out_path.name}")

    print("\n" + "=" * 60)
    print(f"Done. {total_bills} bill(s) written to: {out_dir}")
    print(f"  PREFILLED (amount in QR): {total_prefilled}")
    print(f"  CUSTOM_AMOUNT (amount left blank): {total_custom}")
    print(f"  BOTH (custom amount on top + full amount): {total_both}")
    if errors:
        print(f"  Skipped due to errors: {len(errors)}")
        for e in errors:
            print(f"    - {e}")
    print("=" * 60)


if __name__ == "__main__":
    main()

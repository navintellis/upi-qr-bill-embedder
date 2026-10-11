# Rashi QR Bill Generator — Project Reference

This document is a complete reference to the project for AI assistants (Claude
or others) and human contributors. It should give enough context to safely
make changes without re-reading every file first.

## 1. Purpose

A small, single-script Python tool for **Rashi Heights** society that takes a
quarterly maintenance-bill PDF (exported from the "SocietyMaxx" billing
system, one page per flat/shop) and stamps a scannable **UPI payment QR
code** onto every page, producing one output PDF per flat/shop.

Three QR modes per flat/shop, controlled by a CSV lookup table:

- **PREFILLED** — QR encodes the UPI payment request with the bill's Grand
  Total baked in as the amount. The payer just confirms and pays.
- **CUSTOM_AMOUNT** — QR omits the amount field. The payer types the amount in
  themselves when scanning (mirrors a generic/static personal UPI QR).

- **BOTH** — two QRs on the bill: the PREFILLED (full amount) QR at the usual
  bottom-right position, and the CUSTOM_AMOUNT (custom amount) QR in the blank box at
  the top right (x 515–570, y 118–183pt, with a two-line caption).

Any flat/shop not listed in the CSV defaults to `PREFILLED`.

## 2. Repository layout

```
rashi_project/
├── generate_qr_bills.py          # the entire application (single script)
├── config.json                   # runtime overrides (payee UPI id/name, captions, folder names)
├── flat_shop_preferences.csv     # FlatNo -> QrCodeAmount ("PREFILLED" | "CUSTOM_AMOUNT")
├── requirements.txt              # Python dependencies
├── input/                        # drop the source society bill PDF(s) here
│   └── README.txt
├── output/                       # generated bills land here, per run
│   ├── README.txt
│   └── <yyyymmdd_hhmmss>/        # fresh timestamped folder created every run
├── linux/
│   ├── setup.sh                  # creates venv, installs requirements
│   └── generate.sh               # activates venv, runs generate_qr_bills.py
├── windows/
│   ├── setup.bat                 # Windows equivalent of setup.sh
│   └── generate.bat              # Windows equivalent of generate.sh
└── docs/
    └── PROJECT_REFERENCE.md      # this file
```

There is no package structure, no tests, and no build system — it's a
single-file batch-processing script meant to be run locally by the society's
bill administrator.

## 3. How it works (pipeline)

All logic lives in `generate_qr_bills.py`. High-level flow in `main()`:

1. **Locate input.** Glob every `*.pdf` in `input/` (sorted). Fail fast with a
   clear message if the folder or any PDFs are missing.
2. **Load preferences.** Parse `flat_shop_preferences.csv` into a dict of
   `normalized flat/shop key -> "PREFILLED" | "CUSTOM_AMOUNT"` (see §5).
3. **Create an output run folder.** `output/<yyyymmdd_hhmmss>/`, one per
   script invocation — old runs are never overwritten or cleaned up.
4. **For each input PDF, for each page:**
   - Extract text with `pdfplumber` and parse fields with `extract_fields()`
     (see §4): society name, flat/shop number, Grand Total amount, billing
     quarter/financial year.
   - Look up the flat/shop's QR mode in the preferences dict (default
     `PREFILLED` if absent).
   - Build the `upi://pay?...` URI (`build_upi_uri()`), with or without the
     `am=` amount parameter depending on mode.
   - Render the URI as a QR PNG in memory (`make_qr_image_bytes()`, via the
     `qrcode` library).
   - Build a one-page ReportLab overlay containing the QR image plus a small
     caption ("Scan to Pay Full Amount\nRs.{amount}" or "Scan to Pay Custom
     Amount"), positioned at fixed PDF-point coordinates (`build_overlay()`).
   - Merge the overlay onto the original page (`pypdf` `merge_page`).
   - Write that single page out as its own PDF file into the run folder,
     named `<FlatNo>_Q<quarter>_<fy_start>-<fy_end>_Rashi_Heights_maintenance_bill.pdf`.
     Filename collisions get `_2`, `_3`, ... suffixes (`unique_path()`).
   - Any page that fails field extraction is skipped (not fatal to the run)
     and recorded in an `errors` list.
5. **Print a summary**: total bills written, split by PREFILLED/CUSTOM_AMOUNT count,
   plus any skipped-page errors.

## 4. Bill field extraction (`extract_fields`)

Parses the plain text `pdfplumber` extracts from one PDF page. This is
**tightly coupled to the current SocietyMaxx bill template** — if the
society's billing software changes its export format, these rules likely
need updating:

- `society_name` — first non-blank line of the page, trailing `.` stripped.
- `flat_no` — text after a line starting with literal `Flat No.`.
- `amount` — regex `Grand Total\s*:\s*([\d,]+\.\d{2})`, commas stripped.
- Billing period — regex
  `Bill for the Period\s+([A-Za-z]+)-(\d{4})\s+to\s+([A-Za-z]+)-(\d{4})`,
  using only the **start** month/year.
  - Quarter is derived from the start month against the Indian financial
    year (Apr–Jun = Q1, Jul–Sep = Q2, Oct–Dec = Q3, Jan–Mar = Q4).
  - Financial year (`fy_start`–`fy_end`) is derived the same way (FY starts
    in April).

Any missing/unparseable field raises `ValueError`, which the caller in
`main()` catches, skips the page, and logs.

## 5. `flat_shop_preferences.csv`

Two columns, header required:

| Column        | Values                        |
|---------------|--------------------------------|
| `FlatNo`      | Must match the bill's "Flat No." text (e.g. `201`, `SHOP 1`) |
| `QrCodeAmount`| `PREFILLED`, `CUSTOM_AMOUNT` or `BOTH` (anything else/blank is treated as `PREFILLED`) |

Matching is whitespace-normalized and case-insensitive
(`normalize_key()`: collapse internal whitespace, uppercase). Rows with an
empty `FlatNo` are ignored. If the file is missing entirely, every bill
defaults to `PREFILLED` (a warning is printed).

## 6. `config.json`

Optional. Any key omitted falls back to `DEFAULT_APP_CONFIG` in the script.

```json
{
  "input_dir": "input",
  "output_dir": "output",
  "preferences_file": "flat_shop_preferences.csv",
  "payee_upi_id": "yourname@upi",
  "payee_default_name": "RASHI HEIGHTS CHS LTD",
  "upi_ver": "01",
  "upi_mode": "01",
  "upi_orgid": "123456",
  "upi_mc": "1520",
  "upi_mid": "your-merchant-id",
  "upi_mtid": "your-merchant-id",
  "upi_qr_medium": "04",
  "caption_prefilled": "Scan to Pay Full Amount\nRs.{amount}",
  "caption_custom": "Scan to Pay Custom Amount",
  "caption_both_top": ["Pay Custom", "Amount"],
  "remarks_suffix": "Maintenance"
}
```

- `payee_upi_id` — the VPA (`pa=` param) that appears in every generated QR.
  Currently the society's bank-issued **merchant** VPA (Bank of India),
  taken from the official Rashi Heights CHS Ltd. QR code — not a personal
  UPI handle.
- `payee_default_name` — the `pn=` param shown to the payer's UPI app
  (`"RASHI HEIGHTS CHS LTD"`). If set to `null`/empty, the script falls back
  to the society name parsed off the bill itself.
- `upi_ver`, `upi_mode`, `upi_orgid`, `upi_mc`, `upi_mid`, `upi_mtid`,
  `upi_qr_medium` — static merchant-QR fields copied verbatim from the
  society's bank-issued UPI QR (`mode=01` = static merchant QR, `mc` =
  merchant category code, `mid`/`mtid` = merchant/terminal IDs assigned by
  the bank). Leave any of these as `""` to omit that param entirely — this
  is what makes `build_upi_uri()` also work for a plain personal VPA with
  none of them set.
- `caption_prefilled` / `caption_custom` — text rendered under the QR;
  `caption_prefilled` supports a `{amount}` placeholder, and `\n` in any caption starts a new line (8pt line spacing).
- `caption_both_top` — two caption lines under the top-right QR in `BOTH` mode (`{amount}` supported).
- `remarks_suffix` — additional: trailing word of the UPI remarks (`tn=`),
  i.e. `"<FlatNo> Q<quarter> <fy_start>-<fy_end> <remarks_suffix>"`. Defaults
  to `"Maintenance"` if omitted.
- `input_dir` / `output_dir` / `preferences_file` — relative to the project
  root (`BASE_DIR`, the script's own directory); override if you want a
  different folder layout.

## 7. UPI QR payload format

Built by `build_upi_uri()` as a UPI deep link. The merchant-identity params
(`ver` through `qrMedium`) are emitted in the **exact same order and values
as the society's bank-issued merchant QR**, identically in both QR modes;
`cu` and `tn` are always appended after them (also identical in both modes);
`am` is the **only** parameter that differs between the two modes:

```
upi://pay?ver=<ver>&mode=<mode>&orgid=<orgid>&pa=<vpa>&pn=<name>&mc=<mc>&mid=<mid>&mtid=<mtid>&qrMedium=<qrMedium>&am=<amount>&cu=INR&tn=<remarks>
```

- `ver`/`mode`/`orgid`/`mc`/`mid`/`mtid`/`qrMedium` are each only included
  when the corresponding config value is non-empty (see §6) — this lets
  `build_upi_uri()` also work for a plain personal VPA with none of them set.
- `am=` is present only in `PREFILLED` mode; every other param is identical
  between `PREFILLED` and `CUSTOM_AMOUNT` for the same flat/bill.
- `cu=INR` and `tn=<remarks>` are not present on the society's raw static QR
  but are kept intentionally in the generated per-bill QR: `tn` is what
  encodes `"<FlatNo> Q<quarter> <fy_start>-<fy_end> <remarks_suffix>"` so
  payments can be reconciled back to a specific flat/quarter. (Decision
  recorded 2026-09-23: keep `cu`/`tn` rather than stripping to a byte-exact
  match of the static QR, since dropping `tn` would break payment tracking.)
- All dynamic values are URL-encoded (`urllib.parse.quote`), with `@`
  preserved unescaped in the VPA.

## 8. QR/caption placement on the page

Fixed PDF-point coordinates (top-left origin) tuned specifically for the
current Rashi Heights / SocietyMaxx bill template layout, chosen to sit in a
blank zone clear of existing text/rects/curves:

- QR box: `x: 484–544`, `y: 540–600` (60×60pt).
- `BOTH` mode adds a second QR in the top-right box: `TOP_QR_X0/X1` (517–571), `TOP_QR_TOP0/TOP1` (114–168), caption lines at 176/183pt, Helvetica-Bold 6pt. In this mode the top QR is the custom-amount one and the bottom QR is the full-amount one.
- Caption baseline: 10pt below the QR box, horizontally centered on it,
  Helvetica-Bold 7pt.

If the bill template's page layout ever changes, these constants
(`QR_X0/X1`, `QR_TOP0/TOP1`, `CAPTION_BASELINE_TOP` near the top of
`generate_qr_bills.py`) are the first thing to re-tune.

## 9. Running it

**First-time setup** (creates a `venv/` and installs `requirements.txt`):

```bash
# Linux/macOS
./linux/setup.sh

# Windows
windows\setup.bat
```

**Generate bills** (after placing the source PDF(s) in `input/` and
reviewing `flat_shop_preferences.csv`):

```bash
# Linux/macOS
./linux/generate.sh

# Windows
windows\generate.bat
```

Or directly, with the venv already active:

```bash
python generate_qr_bills.py
```

Each run creates a brand-new `output/<yyyymmdd_hhmmss>/` folder; nothing in
`output/` is ever overwritten in place.

## 10. Dependencies (`requirements.txt`)

- `pdfplumber` — extracts text from the source bill PDF pages.
- `pypdf` — reads the source PDF and merges the QR overlay onto each page.
- `reportlab` — draws the QR image + caption onto a one-page overlay PDF.
- `qrcode[pil]` + `pillow` — generates the QR code PNG.

Python 3.9+ expected (per the setup scripts' messaging).

## 11. Known constraints / things to watch when modifying

- **Template-fragile**: field extraction (§4) and QR placement (§8) both
  assume the exact text layout and page geometry of the current SocietyMaxx
  export. A template change on the billing-software side will likely break
  extraction silently-per-page (pages get skipped, not a hard crash) or shift
  the QR into occupied space.
- **No tests.** Changes should be manually verified by running against a
  real (or redacted sample) input PDF and visually checking a generated
  output PDF plus scanning the QR with a UPI app.
- **No dedup/cleanup of `output/`.** Every run adds a new timestamped folder;
  old runs accumulate on disk indefinitely.
- **Sensitive data**: `flat_shop_preferences.csv` itself only holds flat
  numbers and a QR-mode flag (no personal data). The `input/`/`output/` PDFs
  do contain resident billing amounts and flat numbers — treat them as
  local, non-shared data when working in this repo.

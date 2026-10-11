# UPI QR Bill Embedder

Batch-embed a scannable **UPI payment QR code** into your existing housing-society maintenance bills.

Give it the bill PDF you already have, one page per flat/shop. It reads each page, builds a UPI payment link, and writes one PDF per flat with the QR placed in a blank area of the bill. It does not create bills; it adds the QR to bills you already have. Residents scan it with any UPI app (GPay, PhonePe, Paytm, BHIM, ...) and pay.

> The QR position is tuned for the **SocietyMaxx**-style bill template. Other layouts may need the coordinates in `generate_qr_bills.py` adjusted.

## Features

- One output PDF per flat/shop, named `<FlatNo>_Q<quarter>_<FY>_..._bill.pdf`
- The bill's Grand Total is read from the PDF and can be embedded in the QR
- Per-flat QR mode, set in a simple CSV:

  | Mode | Behaviour |
  |------|-----------|
  | `PREFILLED` | QR carries the bill amount; the payer just confirms (default) |
  | `CUSTOM_AMOUNT` | QR has no amount; the payer types it in |
  | `BOTH` | Two QRs on the bill: full amount (bottom right) and custom amount (top right) |

- UPI remarks like `A-101 Q2 2026-2027 Maintenance`, so payments can be reconciled to a flat and quarter
- Supports plain personal VPAs and bank-issued merchant QR parameters
- Everything configurable from `config.json`: payee, captions, remarks suffix, folders
- Each run writes into a fresh timestamped folder, so earlier output is never overwritten

## Requirements

- Python 3.9+
- `pdfplumber`, `pypdf`, `reportlab`, `qrcode[pil]`, `pillow` (installed by the setup script)

## Quick start

**Linux / macOS**

```bash
./linux/setup.sh          # creates venv/ and installs dependencies
cp config.json.sample config.json
cp flat_shop_preferences.csv.sample flat_shop_preferences.csv
# edit both files, then put your bill PDF(s) in input/
./linux/generate.sh
```

**Windows**

```bat
windows\setup.bat
copy config.json.sample config.json
copy flat_shop_preferences.csv.sample flat_shop_preferences.csv
rem edit both files, then put your bill PDF(s) in input\
windows\generate.bat
```

Generated bills appear in `output/<yyyymmdd_hhmmss>/`.

## Configuration

### `config.json`

Copy from [config.json.sample](config.json.sample). Any key you omit falls back to the default in the script.

| Key | Purpose |
|-----|---------|
| `payee_upi_id` | UPI ID (VPA) that receives the money |
| `payee_default_name` | Name shown in the payer's UPI app; empty = read from the bill |
| `upi_ver`, `upi_mode`, `upi_orgid`, `upi_mc`, `upi_mid`, `upi_mtid`, `upi_qr_medium` | Merchant-QR fields copied from a bank-issued UPI QR; leave `""` for a personal VPA |
| `caption_prefilled`, `caption_custom`, `caption_both_top` | Text printed under each QR (`{amount}` supported, `\n` = new line) |
| `remarks_suffix` | Last word of the UPI remarks (default `Maintenance`) |
| `input_dir`, `output_dir`, `preferences_file` | Folder layout, relative to the project root |

### `flat_shop_preferences.csv`

Copy from [flat_shop_preferences.csv.sample](flat_shop_preferences.csv.sample).

```csv
FlatNo,QrCodeAmount
101,PREFILLED
102,CUSTOM_AMOUNT
SHOP 1,BOTH
```

A flat not listed here defaults to `PREFILLED`.

## Privacy

`config.json`, `flat_shop_preferences.csv`, `input/` and `output/` are git-ignored. Bills contain residents' flat numbers and amounts, and the config holds your payee details, so none of it should be committed.

## Documentation

See [docs/PROJECT_REFERENCE.md](docs/PROJECT_REFERENCE.md) for how the script works, the UPI payload format and the QR layout.

## License

[MIT](LICENSE)

## Project layout

```
generate_qr_bills.py              main script
config.json.sample                config template
flat_shop_preferences.csv.sample  preferences template
requirements.txt
linux/  windows/                  setup and run scripts
input/  output/                   bills in, stamped bills out
docs/PROJECT_REFERENCE.md
LICENSE
```

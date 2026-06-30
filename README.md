# StockSense — AI Inventory Forecasting & Auto-Reorder SaaS (v1)

A universal **ingestion engine** that normalizes *any* inventory/sales input into one
clean schema, then forecasts demand, suggests reorders, and optimizes for **cash
survivability**. The ingestion + auto-mapping layer is the moat; forecasting math is
deliberately simple and explainable.

## Run

```bash
cd inventory-saas
pip install -r requirements.txt          # streamlit, pandas, numpy, openpyxl
streamlit run app.py
```

In the app sidebar: **Load demo data** → **Generate messy demo Excel** (downloads a
deliberately messy file), then go to **Import data** and upload it to watch the
auto-mapping detect every column despite scrambled order, ₹ signs and mixed dates.

CLI smoke test (no UI):

```bash
python -m core.seed        # seeds DB + writes demo_messy.xlsx
```

> Note: needs a working Python with pandas. On this machine the Homebrew 3.14 is
> broken (pyexpat); use `/opt/anaconda3/bin/python3`.

## The moat — ease of use + one-tap ordering

The forecasting is commodity; the value is that a low-literacy shopkeeper can act
on it in one tap.

* **Language** — English / हिंदी / Hinglish toggle; big tap targets, minimal words.
* **Close the loop (`core/sourcing.py`)** — every reorder suggestion becomes a
  real purchase action, no paid API:
  * **📲 Order on WhatsApp** — one tap sends the exact item+qty list to the shop's
    distributor (kiranas already order on WhatsApp). Whole-list or per-item.
  * **🔍 Find supplier** — deep links to Udaan / IndiaMART / Amazon Business / JioMart.
  * **📞 Call** — tap-to-dial the supplier.
* Set the supplier WhatsApp number + shop name in the sidebar (stored in the
  `settings` table). The **automated daily report also embeds the WhatsApp order
  link**, so even the scheduled popup lets you order in one tap.

## Automation — hands-off auto-sync (macOS)

Stop uploading. Export from your billing software into the `inbox/` folder (or
auto-export there), and a scheduled job ingests it and rewrites the buy-list.

```bash
./schedule_mac.sh install            # auto-sync every 6h (launchd)
INTERVAL_HOURS=1 ./schedule_mac.sh install   # hourly instead
./schedule_mac.sh run-now            # sync immediately
./schedule_mac.sh status             # is it running?
./schedule_mac.sh uninstall          # stop

python automate.py                   # run one sync by hand
python automate.py --init            # write a default automation.json
```

Pipeline: `inbox/*.xlsx|csv → auto-mapping → DB → reports/buy_today.txt + .csv`.
Processed files move to `inbox/archive/` (idempotent — never imported twice);
bad files go to `inbox/errors/`. Per-provider last-sync is in `state.json`.

**Connectors** (`core/adapters/pos/`, listed in the app's 🔄 Auto-sync tab):

| Connector | Status |
|---|---|
| `inbox` | ✅ works today — folder export, any billing tool |
| `tally` | ✅ real — talks to Tally XML gateway at `localhost:9000` (Tally must be running) |
| `vyapar` | 🔌 needs a partner API key — export to inbox meanwhile |
| `marg`, `busy` | 🔌 stubs — export to inbox meanwhile |

Edit `automation.json` to enable/disable connectors and set a `cash_cap` for the
report. Add a new billing integration by implementing `POSIntegration.sync()` and
registering it in `core/adapters/pos/providers.py`.

**Daily budget (`cash_cap`)** — set a number in `automation.json` and every report
plans within that budget (buys highest-priority items first, lists the rest as
"over budget"). `null` = plan to buy everything.

**Delivery (`notify`)** — after each run the report is pushed to you:

| Channel | Status | Setup |
|---|---|---|
| `macos` | ✅ on by default | desktop popup, no setup |
| `email` | ✅ real (SMTP) | set `host/port/user/password/to` in `automation.json` (or `SMTP_*` env vars). Gmail: use an App Password |
| `whatsapp` | 🔌 stub | needs a paid provider (Twilio/Meta) — see `core/notify.py` |

Secrets live in `automation.json` (gitignored) or env vars — never hardcoded.

## Normalized schema (single source of truth)

`products(sku, name, unit_cost)` · `sales(sku, date, qty)` ·
`inventory(sku, on_hand, updated_at)` · `suppliers(sku, lead_time_days, reliability)` ·
`outcomes(sku, date, forecast_qty, actual_qty, stockout, spoilage, lead_time_actual)`

Every input type → **adapter** → these tables. See `core/db.py`, `core/schema.py`.

## V1 (built, working)

| # | Feature | Where |
|---|---|---|
| 1 | **Flexible Excel/CSV importer w/ AUTO column-mapping** (header synonyms + value-type inference, multilingual hints, shows confidence, user-correctable) | `core/mapping.py`, `core/adapters/tabular.py`, Import page |
| 2 | Manual-entry fallback | `core/adapters/manual.py`, Manual page |
| 3 | **Per-SKU explainable forecast** — moving-avg + linear trend; **Croston** auto-selected for intermittent/lumpy spare-parts demand | `core/forecast.py` |
| 4 | **Reorder engine** — reorder point = lead-time demand + safety stock (service-level z, supplier-reliability padding); order-up-to qty. Suggest-only, human approves | `core/reorder.py` |
| 5 | **Cash-flow / survivability optimizer** — "reorder everything = ₹X" vs lean plan under a cash cap, prioritising velocity × risk × critical; flags slow/dead movers to skip; partial-fills high-risk SKUs | `core/cashflow.py`, Cash-flow page |
| 6 | Dashboard — stock, forecast, stockout risk, reorder suggestions, cash impact | `app.py` |

## Later features — scaffolded stubs (interfaces + TODOs, not built)

| Feature | Plug-in point | Notes |
|---|---|---|
| **A. Printed bill / PO OCR** | `core/adapters/ocr_printed.py` | implement `normalize(bytes)`; high-trust |
| **B. Handwritten register OCR (beta)** | `core/adapters/ocr_handwritten.py` | `needs_confirmation=True` always — mandatory "here's what I read" review; never auto-acts |
| **C. POS integration** (Vyapar→Tally→Marg→Busy) | `core/adapters/pos/` | `POSIntegration.sync()` per provider; registry drives UI |
| **D. Market-rate / supplier-price linking** | `core/adapters/supplier_price.py` | `SupplierPriceSource` interface; **no scraping** — feed/price-book impls later |
| **E. Crisis / demand-drop guard** | `core/cashflow.py:crisis_guard` | **live rule already wired** into Cash-flow page; TODO smarter signals |
| **F. Auto-reorder (post-trust)** | `core/autoreorder.py` | per-SKU toggle + `is_trusted()` score from outcomes; v1 never auto-buys |

## Outcome-data flywheel

`outcomes` table captures forecast-vs-actual, stockouts, spoilage and lead-time actuals
from day one (`core/outcomes.py`). It feeds the auto-reorder **trust score** (F) and is
the compounding long-term moat.

## How an adapter plugs in

Implement `Adapter.normalize(raw) -> NormalizedBatch` (`core/adapters/base.py`). Return
canonical `products/sales/inventory/suppliers` rows; set `needs_confirmation=True` for
low-trust sources. The rest of the system treats every source identically.
```
raw input ──▶ adapter.normalize() ──▶ NormalizedBatch ──▶ db upserts ──▶ engine ──▶ UI
```
```
core/
  schema.py  db.py  mapping.py  forecast.py  reorder.py  cashflow.py
  engine.py  outcomes.py  autoreorder.py  seed.py
  adapters/  base.py tabular.py manual.py ocr_printed.py ocr_handwritten.py
             supplier_price.py  pos/{base,providers}.py
app.py
```

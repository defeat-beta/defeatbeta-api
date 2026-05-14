---
name: defeatbeta-dcf
description: "Generate a fully editable Discounted Cash Flow (DCF) valuation spreadsheet for a public company. Builds a single-sheet Excel workbook with WACC, growth estimates, 10-year FCF projections, and fair price — all wired as live formulas so users can flex discount rate or growth assumptions and see fair price update. Triggers on DCF analysis, discounted cash flow, intrinsic value, fair price estimate, build a DCF model, value [company]."
argument-hint: <TICKER>
compatibility: Requires defeatbeta MCP server and openpyxl. LibreOffice (headless) is optional but recommended for cached cell values in previewers.
---

# DCF Valuation Spreadsheet

Build a fully editable, formula-driven DCF model for a public company. All inputs come from the `defeatbeta` MCP server's `get_stock_dcf_analysis` tool. The skill renders the data into a single-sheet `.xlsx` whose every projection, NPV, and fair-price cell is an Excel formula — so the user can change the discount rate, growth-rate assumptions, cash, or share count and watch fair price recalculate.

## Workflow

### Step 1: Fetch DCF data via MCP

Call the MCP tool:

```
get_stock_dcf_analysis(symbol="<TICKER>")
```

If the response contains an `error` key (e.g. ETFs / indices without financial statements), stop and surface the error to the user.

### Step 2: Save the payload to a temporary JSON

```bash
# Pseudocode — Claude writes the dict returned by MCP to a temp file
echo "<dcf-data-as-json>" > /tmp/<TICKER>_dcf.json
```

### Step 3: Build the Excel workbook

Run the build script from this skill:

```bash
python <SKILL_DIR>/scripts/build_dcf_excel.py /tmp/<TICKER>_dcf.json ./<TICKER>_DCF.xlsx
```

- Output is `{SYMBOL}_DCF.xlsx` in the current working directory by default.
- Override path by passing it as the second argument.

### Step 4: Recalculate so previewers show numbers

`openpyxl` writes formula strings but does not evaluate them. Most spreadsheet apps recalc on open, but lightweight previewers (and Claude's file preview) need cached values:

```bash
python <SKILL_DIR>/scripts/recalc.py ./<TICKER>_DCF.xlsx
```

The recalc script uses `libreoffice --headless --calc` to evaluate every formula and write the cached value back into the file. If LibreOffice is not on `PATH`, the script prints a warning and exits cleanly — the workbook is still valid, it will just show blank cells in previewers until opened in Excel/Numbers/WPS.

Install LibreOffice if you want in-Claude preview to show numbers:

- macOS: `brew install --cask libreoffice`
- Debian/Ubuntu: `sudo apt-get install libreoffice-calc`
- Other: see https://www.libreoffice.org/download/

### Step 5: Surface the file to the user

Tell the user the output path and call out what is editable:

> Generated `AAPL_DCF.xlsx`. Editable cells (light grey fill, blue font) drive everything downstream: change the discount rate or growth rates in the DCF Template section to see fair price update.

## Workbook Layout

Single sheet, four vertical sections:

1. **Discount Rate (WACC)** — Market cap, beta, debt, interest expense, risk-free rate, expected market return → derives weights, cost of debt/equity, WACC. WACC is a live formula.
2. **Growth Estimates** — 3-year historical revenue with computed 3Y CAGR; up to 10 annual EPS TTM snapshots with computed multi-year CAGR; 5-year annual 10Y Treasury averages.
3. **DCF Template** — Future growth rate assumptions (1–5Y, 6–10Y, terminal), discount rate, TTM revenue, base FCF, then a 10-year FCF / Terminal Value / Total Value / FCF Margin grid. Years 1–5 grow at the near-term rate; years 6–10 use linear interpolation toward terminal.
4. **DCF Value** — Enterprise Value via `NPV(discount_rate, Total Value year 1..10)`, plus cash and debt → equity value → fair price → margin of safety → Buy/Sell recommendation.

### Color & font conventions

| Element | Fill | Font |
|---|---|---|
| Section headers | Dark blue `#1F4E79` | White bold |
| Column headers (year labels) | Light blue `#D9E1F2` | Black bold |
| Input cells (user-editable assumptions) | Light grey `#F2F2F2` | Blue `#0000FF` |
| Formula cells | White | Black |
| Key totals (WACC, Fair Price, MoS) | Medium blue `#BDD7EE` | Black bold |

The user can identify what is editable at a glance: anything in blue font on a grey background is fair game; black-on-white is a derived formula.

## Notes for the assistant

- The MCP tool returns numeric values already (TTM, base FCF, historical CAGRs as cached values). The build script writes those as **input cells** and derives every projection / valuation cell via formula referencing the inputs. Never paste a pre-computed projection into the sheet — write the formula.
- `dcf_template.projections[0]` is the TTM base (year 0). Years 1–10 are formula columns.
- `terminal_value` is non-zero only at year 10.
- `recommendation` is `"Buy"` or `"Sell"` (mixed case, not all-caps).
- After recalc, sanity check: the workbook's computed `fair_price` should match `dcf_value.fair_price` from the MCP payload to within rounding.

## Failure modes

- **MCP returns `error`** (no financials): tell the user, do not generate Excel.
- **LibreOffice not installed**: recalc step prints a warning; the .xlsx is still valid for Excel/Numbers users.
- **Formula references broken**: the build script writes deterministic cell addresses (no dynamic offsets), so this should not happen — if it does, regenerate.

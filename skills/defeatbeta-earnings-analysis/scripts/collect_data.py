"""Collect all Tier-1 and Tier-2 earnings-analysis data for a ticker into local
files, so the assistant doesn't have to pull dozens of MCP tools' worth of
data through its own context window.

The script imports defeatbeta-api MCP tool functions directly (bypassing the
MCP protocol) and writes each data domain to a separate file in the chosen
output directory. The assistant then reads only the files it needs at each
report-writing step, drastically reducing context pressure.

Output files (under --output-dir):
    _summary.json              — selected period + key KPIs + file inventory
    statements.json            — quarterly income/balance/cashflow (combined)
    transcript_current.txt     — earnings call transcript for target period
    transcript_prior.txt       — prior-quarter transcript (for prior guidance)
    valuation.json             — P/E, EV/*, P/S, P/B, PEG, WACC, DCF, mkt cap, price, EPS
    margins.json               — gross/op/net/EBITDA/FCF margins (history)
    growth.json                — revenue/op-income/ebitda/net-income/fcf/EPS YoY (history)
    capital_efficiency.json    — ROIC, ROE, ROA, asset turnover, equity multiplier, D/E
    segment.json               — segment revenue (history)
    geography.json             — geography revenue (history)
    industry.json              — industry benchmarks (TTM P/E, P/S, P/B, margins, returns)

Usage:
    python collect_data.py \
        --ticker AMD \
        --output-dir /tmp/defeatbeta_mcp/AMD \
        [--fiscal-year 2025] \
        [--fiscal-quarter 1]

If --fiscal-year / --fiscal-quarter are omitted, the latest available
transcript is selected automatically.

Behavior:
- Fail-fast: any MCP tool error causes the script to exit with a nonzero
  status. There is no partial recovery; the assistant handles the error.
- Output dir must be writable. Existing files are overwritten.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional

# When running from inside the defeatbeta-api repo (skills/.../scripts/collect_data.py),
# add mcp/src to sys.path so defeatbeta_mcp can be imported without pip-install.
# When defeatbeta-mcp is pip-installed (e.g. in cowork / production), this is a no-op.
_this_dir = os.path.dirname(os.path.abspath(__file__))
_repo_root = os.path.abspath(os.path.join(_this_dir, "..", "..", ".."))
_mcp_src = os.path.join(_repo_root, "mcp", "src")
if os.path.isdir(_mcp_src) and _mcp_src not in sys.path:
    sys.path.insert(0, _mcp_src)

# defeatbeta MCP tools — direct Python imports (no MCP protocol)
from defeatbeta_mcp.tools.asserts import (
    get_stock_quarterly_asset_turnover,
    get_industry_quarterly_asset_turnover,
)
from defeatbeta_mcp.tools.breakdown import (
    get_quarterly_revenue_by_segment,
    get_quarterly_revenue_by_geography,
)
from defeatbeta_mcp.tools.cap import get_stock_market_capitalization
from defeatbeta_mcp.tools.dcf import get_stock_dcf_analysis
from defeatbeta_mcp.tools.de import get_stock_quarterly_debt_to_equity
from defeatbeta_mcp.tools.em import (
    get_stock_quarterly_equity_multiplier,
    get_industry_quarterly_equity_multiplier,
)
from defeatbeta_mcp.tools.eps import get_stock_eps_and_ttm_eps
from defeatbeta_mcp.tools.ev import (
    get_stock_enterprise_value,
    get_stock_enterprise_to_revenue,
    get_stock_enterprise_to_ebitda,
)
from defeatbeta_mcp.tools.growth import (
    get_stock_quarterly_revenue_yoy_growth,
    get_stock_quarterly_operating_income_yoy_growth,
    get_stock_quarterly_ebitda_yoy_growth,
    get_stock_quarterly_net_income_yoy_growth,
    get_stock_quarterly_fcf_yoy_growth,
    get_stock_quarterly_diluted_eps_yoy_growth,
    get_stock_quarterly_ttm_diluted_eps_yoy_growth,
)
from defeatbeta_mcp.tools.margin import (
    get_stock_quarterly_gross_margin,
    get_stock_quarterly_operating_margin,
    get_stock_quarterly_net_margin,
    get_stock_quarterly_ebitda_margin,
    get_stock_quarterly_fcf_margin,
    get_industry_quarterly_gross_margin,
    get_industry_quarterly_ebitda_margin,
    get_industry_quarterly_net_margin,
)
from defeatbeta_mcp.tools.meta import get_latest_data_update_date
from defeatbeta_mcp.tools.pb import get_stock_pb_ratio, get_industry_pb_ratio
from defeatbeta_mcp.tools.pe import get_stock_ttm_pe, get_industry_ttm_pe
from defeatbeta_mcp.tools.peg import get_stock_peg_ratio
from defeatbeta_mcp.tools.price import get_stock_price
from defeatbeta_mcp.tools.ps import get_stock_ps_ratio, get_industry_ps_ratio
from defeatbeta_mcp.tools.roa import (
    get_stock_quarterly_roa,
    get_industry_quarterly_roa,
)
from defeatbeta_mcp.tools.roe import (
    get_stock_quarterly_roe,
    get_industry_quarterly_roe,
)
from defeatbeta_mcp.tools.roic import get_stock_quarterly_roic
from defeatbeta_mcp.tools.statement import (
    get_stock_quarterly_income_statement,
    get_stock_quarterly_balance_sheet,
    get_stock_quarterly_cash_flow,
)
from defeatbeta_mcp.tools.transcripts import (
    get_stock_earning_call_transcripts_list,
    get_stock_earning_call_transcript,
)
from defeatbeta_mcp.tools.wacc import get_stock_wacc


# Tools may return objects pandas DataFrames or custom types; we normalize for JSON.
def _to_jsonable(obj: Any) -> Any:
    try:
        # pandas DataFrame
        import pandas as pd

        if isinstance(obj, pd.DataFrame):
            return obj.to_dict(orient="records")
        if isinstance(obj, pd.Series):
            return obj.to_dict()
    except ImportError:
        pass
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_jsonable(x) for x in obj]
    if hasattr(obj, "isoformat"):  # date / datetime / Timestamp
        return obj.isoformat()
    return obj


def write_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_to_jsonable(payload), f, indent=2, ensure_ascii=False, default=str)


def pick_target_period(
    transcripts_list: Dict[str, Any],
    user_fy: Optional[int],
    user_fq: Optional[int],
) -> Dict[str, Any]:
    """Choose the target fiscal_year / fiscal_quarter.

    If the user supplied --fiscal-year and --fiscal-quarter, find the matching
    record. Otherwise pick the most recent transcript by (fiscal_year,
    fiscal_quarter, report_date) tuple.
    """
    records = transcripts_list.get("transcripts") if isinstance(
        transcripts_list, dict
    ) else transcripts_list
    if not records:
        raise SystemExit(
            "No earnings transcripts found for this ticker — the company may not have "
            "reported under DefeatBeta coverage."
        )

    if user_fy is not None and user_fq is not None:
        for r in records:
            if r.get("fiscal_year") == user_fy and r.get("fiscal_quarter") == user_fq:
                return r
        raise SystemExit(
            f"Requested fiscal_year={user_fy} fiscal_quarter={user_fq} not present in "
            f"transcripts list. Available periods: "
            f"{[(r.get('fiscal_year'), r.get('fiscal_quarter')) for r in records[-8:]]}"
        )

    # Latest by tuple
    sorted_records = sorted(
        records,
        key=lambda r: (
            r.get("fiscal_year") or 0,
            r.get("fiscal_quarter") or 0,
            r.get("report_date") or "",
        ),
    )
    return sorted_records[-1]


def find_prior_period(
    transcripts_list: Dict[str, Any], current: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Return the transcript record immediately preceding `current`, or None."""
    records = transcripts_list.get("transcripts") if isinstance(
        transcripts_list, dict
    ) else transcripts_list
    sorted_records = sorted(
        records,
        key=lambda r: (
            r.get("fiscal_year") or 0,
            r.get("fiscal_quarter") or 0,
            r.get("report_date") or "",
        ),
    )
    idx = None
    for i, r in enumerate(sorted_records):
        if (
            r.get("fiscal_year") == current.get("fiscal_year")
            and r.get("fiscal_quarter") == current.get("fiscal_quarter")
        ):
            idx = i
            break
    if idx is None or idx == 0:
        return None
    return sorted_records[idx - 1]


def collect(ticker: str, output_dir: str, fy: Optional[int], fq: Optional[int]) -> None:
    os.makedirs(output_dir, exist_ok=True)

    # === Step 0: dataset date + transcripts list (small, always retrieved) ===
    dataset_info = get_latest_data_update_date()
    transcripts_list = get_stock_earning_call_transcripts_list(ticker)

    current_period = pick_target_period(transcripts_list, fy, fq)
    prior_period = find_prior_period(transcripts_list, current_period)

    target_fy = current_period["fiscal_year"]
    target_fq = current_period["fiscal_quarter"]
    target_report_date = current_period.get("report_date")

    # === Step 1: Quarterly statements (combined) ===
    statements = {
        "income_statement": get_stock_quarterly_income_statement(ticker),
        "balance_sheet": get_stock_quarterly_balance_sheet(ticker),
        "cash_flow": get_stock_quarterly_cash_flow(ticker),
    }
    write_json(os.path.join(output_dir, "statements.json"), statements)

    # === Step 2: Transcripts (current + prior) ===
    current_transcript = get_stock_earning_call_transcript(ticker, target_fy, target_fq)
    transcript_text = _extract_transcript_text(current_transcript)
    with open(os.path.join(output_dir, "transcript_current.txt"), "w", encoding="utf-8") as f:
        f.write(transcript_text)

    if prior_period is not None:
        prior_transcript = get_stock_earning_call_transcript(
            ticker, prior_period["fiscal_year"], prior_period["fiscal_quarter"]
        )
        prior_text = _extract_transcript_text(prior_transcript)
        with open(os.path.join(output_dir, "transcript_prior.txt"), "w", encoding="utf-8") as f:
            f.write(prior_text)

    # === Step 3: Valuation bundle ===
    valuation = {
        "price": get_stock_price(ticker),
        "market_capitalization": get_stock_market_capitalization(ticker),
        "eps_and_ttm_eps": get_stock_eps_and_ttm_eps(ticker),
        "wacc": get_stock_wacc(ticker),
        "dcf_analysis": get_stock_dcf_analysis(ticker),
        "ttm_pe": get_stock_ttm_pe(ticker),
        "ps_ratio": get_stock_ps_ratio(ticker),
        "pb_ratio": get_stock_pb_ratio(ticker),
        "peg_ratio": get_stock_peg_ratio(ticker),
        "enterprise_value": get_stock_enterprise_value(ticker),
        "ev_to_revenue": get_stock_enterprise_to_revenue(ticker),
        "ev_to_ebitda": get_stock_enterprise_to_ebitda(ticker),
    }
    write_json(os.path.join(output_dir, "valuation.json"), valuation)

    # === Step 4: Margins (history) ===
    margins = {
        "gross_margin": get_stock_quarterly_gross_margin(ticker),
        "operating_margin": get_stock_quarterly_operating_margin(ticker),
        "net_margin": get_stock_quarterly_net_margin(ticker),
        "ebitda_margin": get_stock_quarterly_ebitda_margin(ticker),
        "fcf_margin": get_stock_quarterly_fcf_margin(ticker),
    }
    write_json(os.path.join(output_dir, "margins.json"), margins)

    # === Step 5: Growth (history) ===
    growth = {
        "revenue_yoy": get_stock_quarterly_revenue_yoy_growth(ticker),
        "operating_income_yoy": get_stock_quarterly_operating_income_yoy_growth(ticker),
        "ebitda_yoy": get_stock_quarterly_ebitda_yoy_growth(ticker),
        "net_income_yoy": get_stock_quarterly_net_income_yoy_growth(ticker),
        "fcf_yoy": get_stock_quarterly_fcf_yoy_growth(ticker),
        "diluted_eps_yoy": get_stock_quarterly_diluted_eps_yoy_growth(ticker),
        "ttm_diluted_eps_yoy": get_stock_quarterly_ttm_diluted_eps_yoy_growth(ticker),
    }
    write_json(os.path.join(output_dir, "growth.json"), growth)

    # === Step 6: Capital efficiency ===
    capital_efficiency = {
        "roic": get_stock_quarterly_roic(ticker),
        "roe": get_stock_quarterly_roe(ticker),
        "roa": get_stock_quarterly_roa(ticker),
        "asset_turnover": get_stock_quarterly_asset_turnover(ticker),
        "equity_multiplier": get_stock_quarterly_equity_multiplier(ticker),
        "debt_to_equity": get_stock_quarterly_debt_to_equity(ticker),
    }
    write_json(os.path.join(output_dir, "capital_efficiency.json"), capital_efficiency)

    # === Step 7: Segment + geography ===
    write_json(
        os.path.join(output_dir, "segment.json"),
        get_quarterly_revenue_by_segment(ticker),
    )
    write_json(
        os.path.join(output_dir, "geography.json"),
        get_quarterly_revenue_by_geography(ticker),
    )

    # === Step 8: Industry benchmarks ===
    industry = {
        "ttm_pe": get_industry_ttm_pe(ticker),
        "ps_ratio": get_industry_ps_ratio(ticker),
        "pb_ratio": get_industry_pb_ratio(ticker),
        "gross_margin": get_industry_quarterly_gross_margin(ticker),
        "ebitda_margin": get_industry_quarterly_ebitda_margin(ticker),
        "net_margin": get_industry_quarterly_net_margin(ticker),
        "roa": get_industry_quarterly_roa(ticker),
        "roe": get_industry_quarterly_roe(ticker),
        "asset_turnover": get_industry_quarterly_asset_turnover(ticker),
        "equity_multiplier": get_industry_quarterly_equity_multiplier(ticker),
    }
    write_json(os.path.join(output_dir, "industry.json"), industry)

    # === Step 9: _summary.json with file inventory + key KPIs ===
    summary = {
        "ticker": ticker.upper(),
        "dataset_date": dataset_info.get("latest_data_date")
        if isinstance(dataset_info, dict)
        else None,
        "target_period": {
            "fiscal_year": target_fy,
            "fiscal_quarter": target_fq,
            "report_date": target_report_date,
        },
        "prior_period": (
            {
                "fiscal_year": prior_period.get("fiscal_year"),
                "fiscal_quarter": prior_period.get("fiscal_quarter"),
                "report_date": prior_period.get("report_date"),
            }
            if prior_period
            else None
        ),
        "files": {
            "statements": "statements.json",
            "transcript_current": "transcript_current.txt",
            "transcript_prior": (
                "transcript_prior.txt" if prior_period else None
            ),
            "valuation": "valuation.json",
            "margins": "margins.json",
            "growth": "growth.json",
            "capital_efficiency": "capital_efficiency.json",
            "segment": "segment.json",
            "geography": "geography.json",
            "industry": "industry.json",
        },
        "notes": (
            "Tier 3 data (consensus, analyst PT, operating metrics, news) is NOT in this "
            "bundle — fetch from web at report-writing time."
        ),
    }
    write_json(os.path.join(output_dir, "_summary.json"), summary)

    # === Stdout summary (lands in Claude's context — keep it small) ===
    print(f"Collected {ticker.upper()} FY{target_fy} Q{target_fq} "
          f"(reported {target_report_date}). Dataset date: {summary['dataset_date']}.")
    print(f"Output dir: {output_dir}")
    print("Files written:")
    for label, fname in summary["files"].items():
        if fname:
            print(f"  - {fname}  ({label})")
    if prior_period:
        print(f"Prior period for guidance comparison: "
              f"FY{prior_period['fiscal_year']} Q{prior_period['fiscal_quarter']} "
              f"(reported {prior_period.get('report_date')})")
    print()
    print("Tier 3 (consensus, analyst PT, operating metrics, news) NOT included — fetch via web search.")


def _extract_transcript_text(transcript: Any) -> str:
    """Best-effort extraction of plain transcript text from various return shapes."""
    if isinstance(transcript, str):
        return transcript
    if isinstance(transcript, dict):
        # Common patterns: {"transcript": "..."} or {"text": "..."} or {"paragraphs": [...]}
        for key in ("transcript", "text", "content", "body"):
            if key in transcript and isinstance(transcript[key], str):
                return transcript[key]
        if "paragraphs" in transcript and isinstance(transcript["paragraphs"], list):
            return "\n\n".join(
                p.get("text", str(p)) if isinstance(p, dict) else str(p)
                for p in transcript["paragraphs"]
            )
        return json.dumps(_to_jsonable(transcript), indent=2, ensure_ascii=False, default=str)
    return str(transcript)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect Tier-1/Tier-2 earnings data for a ticker into local files."
    )
    parser.add_argument("--ticker", required=True, help="Stock ticker, e.g. AMD")
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write data files into. Will be created if it doesn't exist.",
    )
    parser.add_argument(
        "--fiscal-year",
        type=int,
        default=None,
        help="Target fiscal year. If omitted, the latest available transcript is used.",
    )
    parser.add_argument(
        "--fiscal-quarter",
        type=int,
        default=None,
        help="Target fiscal quarter. Must be paired with --fiscal-year.",
    )
    args = parser.parse_args()

    if (args.fiscal_year is None) != (args.fiscal_quarter is None):
        print(
            "error: --fiscal-year and --fiscal-quarter must be provided together (or both omitted)",
            file=sys.stderr,
        )
        return 2

    collect(
        ticker=args.ticker.upper(),
        output_dir=os.path.abspath(args.output_dir),
        fy=args.fiscal_year,
        fq=args.fiscal_quarter,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

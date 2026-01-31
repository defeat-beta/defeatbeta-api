import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import LinearLocator, FormatStrFormatter, Formatter, PercentFormatter

from defeatbeta_api import __version__, HuggingFaceClient
from defeatbeta_api.data.ticker import Ticker
from defeatbeta_api.utils import util
from defeatbeta_api.utils.util import html_table, human_format
from pathlib import Path

def html(ticker: Ticker, output=None):
    if output is None and not util.in_notebook():
        raise ValueError("`output` must be specified")

    template_path = Path(__file__).parent / 'tearsheet.html'
    template_path = template_path.resolve()
    if not template_path.exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")
    if not template_path.is_file():
        raise ValueError(f"Template path is not a file: {template_path}")
    tpl = template_path.read_text(encoding='utf-8')

    tpl = fill_headline(ticker, tpl)

    tpl = fill_pe(ticker, tpl)

    tpl = fill_quarterly_gross_margin_profitability(ticker, tpl)

    tpl = fill_quarterly_ebitda_margin_profitability(ticker, tpl)

    tpl = fill_quarterly_net_margin_profitability(ticker, tpl)

    tpl = fill_quarterly_revenue_growth(ticker, tpl)

    tpl = fill_quarterly_ebitda_growth(ticker, tpl)

    tpl = fill_quarterly_net_income_growth(ticker, tpl)

    tpl = fill_quarterly_eps_growth(ticker, tpl)

    if util.in_notebook():
        if output is None:
            output = f"{ticker.ticker}.html"
        util.download_html(tpl, output)
    else:
        with open(output, "w", encoding="utf-8") as f:
            f.write(tpl)

def fill_quarterly_eps_growth(ticker: Ticker, tpl):
    stock_eps_growth = ticker.quarterly_eps_yoy_growth()
    stock_eps_growth = stock_eps_growth.dropna(subset=['yoy_growth']).tail(8)
    y_min = stock_eps_growth['yoy_growth'].min()
    y_max = stock_eps_growth['yoy_growth'].max()
    ranges = []
    if y_min < 0:
        ranges.append((y_min, 0.0, "#F7C6C7", "Cornered"))
    if 0 < y_max < 0.1:
        ranges.append((0.0, 0.10, "#F8E5B9", "Slow Growers"))
    if 0.1 < y_max < 0.2:
        ranges.append((0.0, 0.10, "#F8E5B9", "Slow Growers"))
        ranges.append((0.10, 0.20, "#D5F5D0", "Stalwarts"))
    if 0.2 < y_max:
        ranges.append((0.0, 0.10, "#F8E5B9", "Slow Growers"))
        ranges.append((0.10, 0.20, "#D5F5D0", "Stalwarts"))
        ranges.append((0.20, y_max, "#D6EAF8", "Fast Growers"))

    figure = plot_single_series_figure(
        title='Quarterly Diluted EPS YoY Growth',
        series_x=stock_eps_growth['report_date'],
        series_y=stock_eps_growth['yoy_growth'],
        series_label='Quarterly EPS YoY Growth',
        fig_size=(8, 4),
        y_axis_ticks=10,
        formater=PercentFormatter(xmax=1.0, decimals=1),
        figure_type='bar',
        horizontal_lines=[0],
        range_lines=ranges
    )
    tpl = tpl.replace("{{quarterly_eps_yoy_growth}}", util.embed_figure(figure, "svg"))
    tpl = tpl.replace("{{quarterly_eps_yoy_growth_title}}", "<h3>Quarterly Diluted EPS YoY Growth</h3>")
    quarterly_eps_yoy_growth_table = stock_eps_growth[['report_date', 'eps', 'prev_year_eps', 'yoy_growth']].copy()
    quarterly_eps_yoy_growth_table['report_date'] = quarterly_eps_yoy_growth_table['report_date'].dt.date
    quarterly_eps_yoy_growth_table['yoy_growth'] = quarterly_eps_yoy_growth_table['yoy_growth'].apply(
        lambda x: f"{x * 100:.2f}%" if pd.notna(x) else 'NaN'
    )
    quarterly_eps_yoy_growth_table["eps"] = \
        quarterly_eps_yoy_growth_table["eps"].apply(human_format)
    quarterly_eps_yoy_growth_table["prev_year_eps"] = \
        quarterly_eps_yoy_growth_table["prev_year_eps"].apply(human_format)

    quarterly_eps_yoy_growth_table.rename(
        columns={
            'report_date': 'Report Date',
            'eps': 'Current',
            'prev_year_eps': 'Prev. (YoY Base)',
            'yoy_growth': 'YoY %'
        },
        inplace=True
    )

    tpl = tpl.replace("{{quarterly_eps_yoy_growth_table}}", html_table(quarterly_eps_yoy_growth_table, showindex=False))
    return tpl

def fill_quarterly_revenue_growth(ticker: Ticker, tpl):
    stock_revenue_growth = ticker.quarterly_revenue_yoy_growth()
    stock_revenue_growth = stock_revenue_growth.dropna(subset=['yoy_growth']).tail(8)
    y_min = stock_revenue_growth['yoy_growth'].min()
    y_max = stock_revenue_growth['yoy_growth'].max()
    ranges = []
    if y_min < 0:
        ranges.append((y_min, 0.0, "#F7C6C7", "Cornered"))
    if 0 < y_max < 0.1:
        ranges.append((0.0, 0.10, "#F8E5B9", "Slow Growers"))
    if 0.1 < y_max < 0.2:
        ranges.append((0.0, 0.10, "#F8E5B9", "Slow Growers"))
        ranges.append((0.10, 0.20, "#D5F5D0", "Stalwarts"))
    if 0.2 < y_max:
        ranges.append((0.0, 0.10, "#F8E5B9", "Slow Growers"))
        ranges.append((0.10, 0.20, "#D5F5D0", "Stalwarts"))
        ranges.append((0.20, y_max, "#D6EAF8", "Fast Growers"))

    figure = plot_single_series_figure(
        title='Quarterly Revenue YoY Growth',
        series_x=stock_revenue_growth['report_date'],
        series_y=stock_revenue_growth['yoy_growth'],
        series_label='Quarterly Revenue YoY Growth',
        fig_size=(8, 4),
        y_axis_ticks=10,
        formater=PercentFormatter(xmax=1.0, decimals=1),
        figure_type='bar',
        horizontal_lines=[0],
        range_lines=ranges
    )
    tpl = tpl.replace("{{quarterly_revenue_yoy_growth}}", util.embed_figure(figure, "svg"))
    tpl = tpl.replace("{{quarterly_revenue_yoy_growth_title}}", "<h3>Quarterly Revenue YoY Growth</h3>")
    quarterly_revenue_yoy_growth_table = stock_revenue_growth[['report_date', 'revenue', 'prev_year_revenue', 'yoy_growth']].copy()
    quarterly_revenue_yoy_growth_table['report_date'] = quarterly_revenue_yoy_growth_table['report_date'].dt.date
    quarterly_revenue_yoy_growth_table['yoy_growth'] = quarterly_revenue_yoy_growth_table['yoy_growth'].apply(
        lambda x: f"{x * 100:.2f}%" if pd.notna(x) else 'NaN'
    )
    quarterly_revenue_yoy_growth_table["revenue"] = \
        quarterly_revenue_yoy_growth_table["revenue"].apply(human_format)
    quarterly_revenue_yoy_growth_table["prev_year_revenue"] = \
        quarterly_revenue_yoy_growth_table["prev_year_revenue"].apply(human_format)

    quarterly_revenue_yoy_growth_table.rename(
        columns={
            'report_date': 'Report Date',
            'revenue': 'Current',
            'prev_year_revenue': 'Prev. (YoY Base)',
            'yoy_growth': 'YoY %'
        },
        inplace=True
    )

    tpl = tpl.replace("{{quarterly_revenue_yoy_growth_table}}", html_table(quarterly_revenue_yoy_growth_table, showindex=False))
    return tpl

def fill_quarterly_ebitda_growth(ticker: Ticker, tpl):
    stock_ebitda_growth = ticker.quarterly_ebitda_yoy_growth()
    stock_ebitda_growth = stock_ebitda_growth.dropna(subset=['yoy_growth']).tail(8)
    y_min = stock_ebitda_growth['yoy_growth'].min()
    y_max = stock_ebitda_growth['yoy_growth'].max()
    ranges = []
    if y_min < 0:
        ranges.append((y_min, 0.0, "#F7C6C7", "Cornered"))
    if 0 < y_max < 0.1:
        ranges.append((0.0, 0.10, "#F8E5B9", "Slow Growers"))
    if 0.1 < y_max < 0.2:
        ranges.append((0.0, 0.10, "#F8E5B9", "Slow Growers"))
        ranges.append((0.10, 0.20, "#D5F5D0", "Stalwarts"))
    if 0.2 < y_max:
        ranges.append((0.0, 0.10, "#F8E5B9", "Slow Growers"))
        ranges.append((0.10, 0.20, "#D5F5D0", "Stalwarts"))
        ranges.append((0.20, y_max, "#D6EAF8", "Fast Growers"))

    figure = plot_single_series_figure(
        title='Quarterly EBITDA YoY Growth',
        series_x=stock_ebitda_growth['report_date'],
        series_y=stock_ebitda_growth['yoy_growth'],
        series_label='Quarterly EBITDA YoY Growth',
        fig_size=(8, 4),
        y_axis_ticks=10,
        formater=PercentFormatter(xmax=1.0, decimals=1),
        figure_type='bar',
        horizontal_lines=[0],
        range_lines=ranges
    )
    tpl = tpl.replace("{{quarterly_ebitda_yoy_growth}}", util.embed_figure(figure, "svg"))
    tpl = tpl.replace("{{quarterly_ebitda_yoy_growth_title}}", "<h3>Quarterly EBITDA YoY Growth</h3>")
    quarterly_ebitda_yoy_growth_table = stock_ebitda_growth[['report_date', 'ebitda', 'prev_year_ebitda', 'yoy_growth']].copy()
    quarterly_ebitda_yoy_growth_table['report_date'] = quarterly_ebitda_yoy_growth_table['report_date'].dt.date
    quarterly_ebitda_yoy_growth_table['yoy_growth'] = quarterly_ebitda_yoy_growth_table['yoy_growth'].apply(
        lambda x: f"{x * 100:.2f}%" if pd.notna(x) else 'NaN'
    )
    quarterly_ebitda_yoy_growth_table["ebitda"] = \
        quarterly_ebitda_yoy_growth_table["ebitda"].apply(human_format)
    quarterly_ebitda_yoy_growth_table["prev_year_ebitda"] = \
        quarterly_ebitda_yoy_growth_table["prev_year_ebitda"].apply(human_format)

    quarterly_ebitda_yoy_growth_table.rename(
        columns={
            'report_date': 'Report Date',
            'ebitda': 'Current',
            'prev_year_ebitda': 'Prev. (YoY Base)',
            'yoy_growth': 'YoY %'
        },
        inplace=True
    )

    tpl = tpl.replace("{{quarterly_ebitda_yoy_growth_table}}", html_table(quarterly_ebitda_yoy_growth_table, showindex=False))
    return tpl

def fill_quarterly_net_income_growth(ticker: Ticker, tpl):
    stock_net_income_growth = ticker.quarterly_net_income_yoy_growth()
    stock_net_income_growth = stock_net_income_growth.dropna(subset=['yoy_growth']).tail(8)
    y_min = stock_net_income_growth['yoy_growth'].min()
    y_max = stock_net_income_growth['yoy_growth'].max()
    ranges = []
    if y_min < 0:
        ranges.append((y_min, 0.0, "#F7C6C7", "Cornered"))
    if 0 < y_max < 0.1:
        ranges.append((0.0, 0.10, "#F8E5B9", "Slow Growers"))
    if 0.1 < y_max < 0.2:
        ranges.append((0.0, 0.10, "#F8E5B9", "Slow Growers"))
        ranges.append((0.10, 0.20, "#D5F5D0", "Stalwarts"))
    if 0.2 < y_max:
        ranges.append((0.0, 0.10, "#F8E5B9", "Slow Growers"))
        ranges.append((0.10, 0.20, "#D5F5D0", "Stalwarts"))
        ranges.append((0.20, y_max, "#D6EAF8", "Fast Growers"))

    figure = plot_single_series_figure(
        title='Quarterly Net Income YoY Growth',
        series_x=stock_net_income_growth['report_date'],
        series_y=stock_net_income_growth['yoy_growth'],
        series_label='Quarterly Net Income YoY Growth',
        fig_size=(8, 4),
        y_axis_ticks=10,
        formater=PercentFormatter(xmax=1.0, decimals=1),
        figure_type='bar',
        horizontal_lines=[0],
        range_lines=ranges
    )
    tpl = tpl.replace("{{quarterly_net_income_yoy_growth}}", util.embed_figure(figure, "svg"))
    tpl = tpl.replace("{{quarterly_net_income_yoy_growth_title}}", "<h3>Quarterly Net Income YoY Growth</h3>")
    quarterly_net_income_yoy_growth_table = stock_net_income_growth[['report_date', 'net_income_common_stockholders', 'prev_year_net_income_common_stockholders', 'yoy_growth']].copy()
    quarterly_net_income_yoy_growth_table['report_date'] = quarterly_net_income_yoy_growth_table['report_date'].dt.date
    quarterly_net_income_yoy_growth_table['yoy_growth'] = quarterly_net_income_yoy_growth_table['yoy_growth'].apply(
        lambda x: f"{x * 100:.2f}%" if pd.notna(x) else 'NaN'
    )
    quarterly_net_income_yoy_growth_table["net_income_common_stockholders"] = \
        quarterly_net_income_yoy_growth_table["net_income_common_stockholders"].apply(human_format)
    quarterly_net_income_yoy_growth_table["prev_year_net_income_common_stockholders"] = \
        quarterly_net_income_yoy_growth_table["prev_year_net_income_common_stockholders"].apply(human_format)

    quarterly_net_income_yoy_growth_table.rename(
        columns={
            'report_date': 'Report Date',
            'net_income_common_stockholders': 'Current',
            'prev_year_net_income_common_stockholders': 'Prev. (YoY Base)',
            'yoy_growth': 'YoY %'
        },
        inplace=True
    )

    tpl = tpl.replace("{{quarterly_net_income_yoy_growth_table}}", html_table(quarterly_net_income_yoy_growth_table, showindex=False))
    return tpl

def fill_quarterly_gross_margin_profitability(ticker: Ticker, tpl):
    stock_gross_margin = ticker.quarterly_gross_margin()
    industry_gross_margin = ticker.industry_quarterly_gross_margin()
    stock_gross_margin['report_date'] = pd.to_datetime(stock_gross_margin['report_date'])
    industry_gross_margin['report_date'] = pd.to_datetime(industry_gross_margin['report_date'])
    merged_df = pd.merge_asof(
        stock_gross_margin,
        industry_gross_margin,
        left_on='report_date',
        right_on='report_date',
        direction='backward'
    )
    merged_df = merged_df.dropna(subset=['gross_margin', 'industry_gross_margin'])

    figure = plot_vs_figure(
        title='Gross Margin (vs Industry)',
        target_series_x=merged_df['report_date'],
        target_series_y=merged_df['gross_margin'],
        target_series_label='Stock Gross Margin',
        baseline_series_x=merged_df['report_date'],
        baseline_series_y=merged_df['industry_gross_margin'],
        baseline_series_label='Industry Gross Margin',
        fig_size=(8, 4),
        y_axis_ticks=10,
        formater=PercentFormatter(xmax=1.0, decimals=1),
        figure_type='bar'
    )
    tpl = tpl.replace("{{gross_margin}}", util.embed_figure(figure, "svg"))
    tpl = tpl.replace("{{gross_margin_title}}", "<h3>Gross Margin</h3>")
    gross_margin_table = merged_df[['report_date', 'gross_margin', 'industry_gross_margin']].copy()
    gross_margin_table['report_date'] = gross_margin_table['report_date'].dt.date
    gross_margin_table['gross_margin'] = gross_margin_table['gross_margin'].apply(
        lambda x: f"{x * 100:.2f}%" if pd.notna(x) else 'NaN'
    )
    gross_margin_table['industry_gross_margin'] = gross_margin_table['industry_gross_margin'].apply(
        lambda x: f"{x * 100:.2f}%" if pd.notna(x) else 'NaN'
    )

    gross_margin_table.rename(
        columns={
            'report_date': 'Report Date',
            'gross_margin': f"{ticker.ticker}",
            'industry_gross_margin': f"{industry_gross_margin['industry'].iloc[0]} Industry",
        },
        inplace=True
    )
    tpl = tpl.replace("{{gross_margin_table}}", html_table(gross_margin_table, showindex=False))
    return tpl

def fill_quarterly_net_margin_profitability(ticker, tpl):
    stock_net_margin = ticker.quarterly_net_margin()
    industry_net_margin = ticker.industry_quarterly_net_margin()
    stock_net_margin['report_date'] = pd.to_datetime(stock_net_margin['report_date'])
    industry_net_margin['report_date'] = pd.to_datetime(industry_net_margin['report_date'])
    merged_df = pd.merge_asof(
        stock_net_margin,
        industry_net_margin,
        left_on='report_date',
        right_on='report_date',
        direction='backward'
    )
    merged_df = merged_df.dropna(subset=['net_margin', 'industry_net_margin'])

    figure = plot_vs_figure(
        title='Net Margin (vs Industry)',
        target_series_x=merged_df['report_date'],
        target_series_y=merged_df['net_margin'],
        target_series_label='Stock Net Margin',
        baseline_series_x=merged_df['report_date'],
        baseline_series_y=merged_df['industry_net_margin'],
        baseline_series_label='Industry Net Margin',
        fig_size=(8, 4),
        y_axis_ticks=10,
        formater=PercentFormatter(xmax=1.0, decimals=1),
        figure_type='bar'
    )
    tpl = tpl.replace("{{net_margin}}", util.embed_figure(figure, "svg"))
    tpl = tpl.replace("{{net_margin_title}}", "<h3>Net Margin</h3>")
    net_margin_table = merged_df[['report_date', 'net_margin', 'industry_net_margin']].copy()
    net_margin_table['report_date'] = net_margin_table['report_date'].dt.date
    net_margin_table['net_margin'] = net_margin_table['net_margin'].apply(
        lambda x: f"{x * 100:.2f}%" if pd.notna(x) else 'NaN'
    )
    net_margin_table['industry_net_margin'] = net_margin_table['industry_net_margin'].apply(
        lambda x: f"{x * 100:.2f}%" if pd.notna(x) else 'NaN'
    )

    net_margin_table.rename(
        columns={
            'report_date': 'Report Date',
            'net_margin': f"{ticker.ticker}",
            'industry_net_margin': f"{industry_net_margin['industry'].iloc[0]} Industry"
        },
        inplace=True
    )
    tpl = tpl.replace("{{net_margin_table}}", html_table(net_margin_table, showindex=False))
    return tpl

def fill_quarterly_ebitda_margin_profitability(ticker, tpl):
    stock_ebitda_margin = ticker.quarterly_ebitda_margin()
    industry_ebitda_margin = ticker.industry_quarterly_ebitda_margin()
    stock_ebitda_margin['report_date'] = pd.to_datetime(stock_ebitda_margin['report_date'])
    industry_ebitda_margin['report_date'] = pd.to_datetime(industry_ebitda_margin['report_date'])
    merged_df = pd.merge_asof(
        stock_ebitda_margin,
        industry_ebitda_margin,
        left_on='report_date',
        right_on='report_date',
        direction='backward'
    )
    merged_df = merged_df.dropna(subset=['ebitda_margin', 'industry_ebitda_margin'])

    figure = plot_vs_figure(
        title='EBITDA Margin (vs Industry)',
        target_series_x=merged_df['report_date'],
        target_series_y=merged_df['ebitda_margin'],
        target_series_label='Stock EBITDA Margin',
        baseline_series_x=merged_df['report_date'],
        baseline_series_y=merged_df['industry_ebitda_margin'],
        baseline_series_label='Industry EBITDA Margin',
        fig_size=(8, 4),
        y_axis_ticks=10,
        formater=PercentFormatter(xmax=1.0, decimals=1),
        figure_type='bar'
    )
    tpl = tpl.replace("{{ebitda_margin}}", util.embed_figure(figure, "svg"))
    tpl = tpl.replace("{{ebitda_margin_title}}", "<h3>EBITDA Margin</h3>")
    net_margin_table = merged_df[['report_date', 'ebitda_margin', 'industry_ebitda_margin']].copy()
    net_margin_table['report_date'] = net_margin_table['report_date'].dt.date
    net_margin_table['ebitda_margin'] = net_margin_table['ebitda_margin'].apply(
        lambda x: f"{x * 100:.2f}%" if pd.notna(x) else 'NaN'
    )
    net_margin_table['industry_ebitda_margin'] = net_margin_table['industry_ebitda_margin'].apply(
        lambda x: f"{x * 100:.2f}%" if pd.notna(x) else 'NaN'
    )

    net_margin_table.rename(
        columns={
            'report_date': 'Report Date',
            'ebitda_margin': f"{ticker.ticker}",
            'industry_ebitda_margin': f"{industry_ebitda_margin['industry'].iloc[0]} Industry"
        },
        inplace=True
    )
    tpl = tpl.replace("{{ebitda_margin_table}}", html_table(net_margin_table, showindex=False))
    return tpl

def fill_pe(ticker, tpl):
    df_stock = ticker.ttm_pe().dropna()
    df_ind = ticker.industry_ttm_pe().dropna()
    df_stock['report_date'] = pd.to_datetime(df_stock['report_date'])
    df_ind['report_date'] = pd.to_datetime(df_ind['report_date'])
    df_ind = df_ind.dropna(subset=['industry_pe'])
    start_date = max(df_stock['report_date'].min(), df_ind['report_date'].min())
    df_stock_trim = df_stock[df_stock['report_date'] >= start_date]
    df_ind_trim = df_ind[df_ind['report_date'] >= start_date]
    figure = plot_vs_figure(
        title='TTM P/E Ratio (vs Industry)',
        target_series_x=df_stock_trim['report_date'],
        target_series_y=df_stock_trim['ttm_pe'],
        target_series_label='Stock TTM PE',
        baseline_series_x=df_ind_trim['report_date'],
        baseline_series_y=df_ind_trim['industry_pe'],
        baseline_series_label='Industry TTM P/E',
        fig_size=(8, 4),
        y_axis_ticks=10,
        formater=FormatStrFormatter('%.0f'),
        use_reasonable_range=True
    )
    tpl = tpl.replace("{{ttm_pe}}", util.embed_figure(figure, "svg"))
    tpl = tpl.replace("{{ttm_pe_title}}", "<h3>TTM P/E Ratio</h3>")
    mean = df_stock_trim['ttm_pe'].mean()
    std = df_stock_trim['ttm_pe'].std()
    last_pe = df_stock_trim['ttm_pe'].iloc[-1]
    total_count = df_stock_trim['ttm_pe'].count()
    low_count = (last_pe < df_stock_trim['ttm_pe']).sum()
    percentile_rank = (low_count / total_count) * 100

    ttm_pe_table = pd.DataFrame([
        {'Metrics': 'Current TTM P/E', 'Value': last_pe},
        {'Metrics': 'Current Industry TTM P/E', 'Value': df_ind_trim['industry_pe'].iloc[-1]},
        {'Metrics': 'μ-Line', 'Value': f"{mean:.2f}"},
        {'Metrics': 'u±1σ Band', 'Value': f"{mean - std:.2f} ~ {mean + std:.2f}"},
        {'Metrics': 'Below-History %', 'Value': f"{percentile_rank:.2f}%"},
    ])
    tpl = tpl.replace("{{ttm_pe_table}}", html_table(ttm_pe_table, showindex=False))
    return tpl


def fill_headline(ticker, tpl):
    info = ticker.info()
    tpl = tpl.replace("{{symbol}}", info['symbol'].iloc[0])
    tpl = tpl.replace("{{sector}}", info['sector'].iloc[0])
    tpl = tpl.replace("{{industry}}", info['industry'].iloc[0])
    tpl = tpl.replace("{{web_site}}", info['web_site'].iloc[0])
    tpl = tpl.replace("{{city}}", info['city'].iloc[0])
    tpl = tpl.replace("{{country}}", info['country'].iloc[0])
    tpl = tpl.replace("{{address}}", info['address'].iloc[0])
    tpl = tpl.replace("{{date_range}}", HuggingFaceClient().get_data_update_time())
    tpl = tpl.replace("{{v}}", __version__)
    return tpl

def plot_single_series_figure(
        title: str,
        series_x: pd.Series, series_y: pd.Series, series_label:str,
        fig_size: tuple,
        y_axis_ticks: int,
        formater: Formatter,
        figure_type: str = "line",
        horizontal_lines: list = None,
        range_lines: list = None):
    fig, ax = plt.subplots(figsize = fig_size)
    for spine in ["top", "right", "bottom", "left"]:
        ax.spines[spine].set_visible(False)
    fig.suptitle(title, fontweight="bold", fontsize=15, color="black")
    fig.set_facecolor("white")
    ax.set_facecolor("white")

    x = series_x

    for line in horizontal_lines:
        ax.hlines(y=line, xmin=series_x.iloc[0], xmax=series_x.iloc[-1], colors="#FA2D1A", linewidth=1.0,
                  linestyles="--")

    for low, high, color, label in range_lines:
        ax.fill_between(
            x,
            low,
            high,
            color=color,
            alpha=0.3,
            linewidth=0,
        )
        x_pos = x.iloc[-1]

        y_pos = high - (high - low) * 0.05

        ax.text(
            x_pos,
            y_pos,
            label,
            ha="right",
            va="top",
            fontsize=8,
            alpha=0.5,
            color="#555555",
        )

    if figure_type == "line":
        ax.plot(series_x, series_y, label=series_label, color='#75FA4C', linewidth=1.5)
    elif figure_type == "bar":
        bar_width = pd.Timedelta(days=20)
        ax.bar(series_x, series_y, width=bar_width, label=series_label, color='#75FA4C')
        for x, y in zip(series_x, series_y):
            ax.text(x, y,f"{y:.1%}", ha='center', va='bottom', fontsize=8, color="#333333")
    else:
        raise Exception(f"Unknown figure type: {figure_type}")

    ax.yaxis.set_major_locator(LinearLocator(y_axis_ticks))
    ax.yaxis.set_major_formatter(formater)
    ax.legend()
    ax.grid(color='gray', alpha=0.2, linewidth=0.3)
    fig.autofmt_xdate()
    plt.tight_layout()
    fig_file = util.file_stream()
    fig.savefig(fig_file, format="svg")
    plt.close(fig)
    return fig_file

def plot_vs_figure(
        title: str,
        target_series_x: pd.Series, target_series_y: pd.Series, target_series_label:str, baseline_series_x: pd.Series, baseline_series_y: pd.Series, baseline_series_label:str,
        fig_size: tuple,
        y_axis_ticks: int,
        formater: Formatter,
        use_reasonable_range: bool = False,
        figure_type: str = "line"):
    fig, ax = plt.subplots(figsize = fig_size)
    for spine in ["top", "right", "bottom", "left"]:
        ax.spines[spine].set_visible(False)
    fig.suptitle(title, fontweight="bold", fontsize=15, color="black")
    fig.set_facecolor("white")
    ax.set_facecolor("white")
    if use_reasonable_range:
        plot_reasonable_range(ax, target_series_x, target_series_y)

    if figure_type == "line":
        ax.plot(target_series_x, target_series_y, label=target_series_label, color='#75FA4C', linewidth=1.5)
        ax.plot(baseline_series_x, baseline_series_y, label=baseline_series_label, color='#1F46F4', linewidth=1.5)
    elif figure_type == "bar":
        bar_width = pd.Timedelta(days=20)
        ax.bar(target_series_x - pd.Timedelta(days=10), target_series_y, width=bar_width, label=target_series_label, color='#75FA4C')
        ax.bar(baseline_series_x + pd.Timedelta(days=10), baseline_series_y, width=bar_width, label=baseline_series_label, color='#1F46F4')
        for x, y in zip(target_series_x - pd.Timedelta(days=10), target_series_y):
            ax.text(x, y,f"{y:.1%}", ha='center', va='bottom', fontsize=8, color="#333333")

        for x, y in zip(baseline_series_x + pd.Timedelta(days=10), baseline_series_y):
            ax.text(x, y, f"{y:.1%}", ha='center', va='bottom', fontsize=8, color="#333333")
    else:
        raise Exception(f"Unknown figure type: {figure_type}")

    ax.yaxis.set_major_locator(LinearLocator(y_axis_ticks))
    ax.yaxis.set_major_formatter(formater)
    ax.legend()
    ax.grid(color='gray', alpha=0.2, linewidth=0.3)
    fig.autofmt_xdate()
    plt.tight_layout()
    fig_file = util.file_stream()
    fig.savefig(fig_file, format="svg")
    plt.close(fig)
    return fig_file


def plot_reasonable_range(ax, target_series_x, target_series_y):
    mean = target_series_y.mean()
    std = target_series_y.std()
    y_lower = mean - std
    y_upper = mean + std
    ax.fill_between(
        target_series_x,
        y_lower,
        y_upper,
        color="#75FA4C",
        alpha=0.25,
        linewidth=0,
        label='Reasonable range'
    )
    last_x = target_series_x.iloc[-1]
    last_y = target_series_y.iloc[-1]
    ax.annotate(
        f"{last_y:.2f}",
        xy=(last_x, last_y),
        xytext=(10, 5),
        textcoords="offset points",
        va='bottom', ha='left', fontsize=9, color="#333333",
        arrowprops=dict(arrowstyle='-', color="#333333", lw=0.5, shrinkA=0, shrinkB=0)
    )
    ax.plot([target_series_x.iloc[0], last_x], [mean, mean], linestyle='--', linewidth=0.8, alpha=0.8)
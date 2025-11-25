import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.ticker import LinearLocator, FormatStrFormatter, Formatter, PercentFormatter

from defeatbeta_api import __version__, data_update_time
from defeatbeta_api.data.ticker import Ticker
from defeatbeta_api.utils import util
from defeatbeta_api.utils.util import html_table

try:
    from IPython.core.display import display as iDisplay, HTML as iHTML
except ImportError:
    from IPython.display import display as iDisplay
    from IPython.core.display import HTML as iHTML
from pathlib import Path


def html(
    ticker: Ticker,
    output=None,
):
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

    tpl = fill_quarterly_profitability(ticker, tpl)

    with open(output, "w", encoding="utf-8") as f:
        f.write(tpl)

def fill_quarterly_profitability(ticker, tpl):
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
            'net_margin': 'Net Margin',
            'industry_net_margin': 'Industry Net Margin'
        },
        inplace=True
    )
    tpl = tpl.replace("{{net_margin_table}}", html_table(net_margin_table, showindex=False))
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
    ttm_pe_table = pd.DataFrame([
        {'Metrics': 'Current TTM P/E', 'Value': last_pe},
        {'Metrics': 'Current Industry TTM P/E', 'Value': df_ind_trim['industry_pe'].iloc[-1]},
        {'Metrics': 'μ-Line', 'Value': f"{mean:.2f}"},
        {'Metrics': '±1σ Band', 'Value': f"{mean - std:.2f} ~ {mean + std:.2f}"}])
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
    tpl = tpl.replace("{{date_range}}", data_update_time)
    tpl = tpl.replace("{{v}}", __version__)
    return tpl


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
    fig.suptitle(title, fontweight="bold", fontname="Arial", fontsize=15, color="black")
    fig.set_facecolor("white")
    ax.set_facecolor("white")
    if use_reasonable_range:
        plot_reasonable_range(ax, target_series_x, target_series_y)

    if figure_type == "line":
        ax.plot(target_series_x, target_series_y, label=target_series_label, color='#75FA4C', linewidth=1.5)
        ax.plot(baseline_series_x, baseline_series_y, label=baseline_series_label, color='#1F46F4', linewidth=1.5)
    elif figure_type == "bar":
        bar_width = pd.Timedelta(days=20)
        ax.bar(target_series_x - pd.Timedelta(days=10), target_series_y, width=bar_width, label=target_series_label, color='#75FA4C', alpha=0.85)
        ax.bar(baseline_series_x + pd.Timedelta(days=10), baseline_series_y, width=bar_width, label=baseline_series_label, color='#1F46F4', alpha=0.85)
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
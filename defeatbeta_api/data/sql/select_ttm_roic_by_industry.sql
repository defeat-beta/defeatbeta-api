WITH raw_data AS (
    SELECT
        symbol,
        report_date,
        MAX(CASE WHEN item_name = 'ebit' THEN item_value END) AS ebit,
        MAX(CASE WHEN item_name = 'tax_rate_for_calcs' THEN item_value END) AS tax_rate_for_calcs,
        MAX(CASE WHEN item_name = 'invested_capital' THEN item_value END) AS invested_capital
    FROM
        '{stock_statement}'
    WHERE
        symbol IN ({symbols})
        AND item_name IN ('ebit', 'tax_rate_for_calcs', 'invested_capital')
        AND period_type = 'quarterly'
        AND report_date != 'TTM'
        AND finance_type IN ('income_statement', 'balance_sheet')
    GROUP BY symbol, report_date
),

quarterly_data AS (
    SELECT
        symbol,
        report_date,
        ebit * (1 - tax_rate_for_calcs) AS nopat,
        invested_capital,
        YEAR(report_date::DATE) * 4 + QUARTER(report_date::DATE) AS continuous_id
    FROM raw_data
    WHERE ebit IS NOT NULL AND tax_rate_for_calcs IS NOT NULL AND invested_capital IS NOT NULL
),

ttm_window AS (
    SELECT
        symbol,
        report_date,
        SUM(nopat) OVER (
            PARTITION BY symbol
            ORDER BY CAST(report_date AS DATE)
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS ttm_nopat,
        COUNT(*) OVER (
            PARTITION BY symbol
            ORDER BY CAST(report_date AS DATE)
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS quarter_count,
        -- Ensure the 4 quarters in the window are truly consecutive
        MAX(continuous_id) OVER (
            PARTITION BY symbol
            ORDER BY CAST(report_date AS DATE)
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) - MIN(continuous_id) OVER (
            PARTITION BY symbol
            ORDER BY CAST(report_date AS DATE)
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS id_range,
        invested_capital AS ending_invested_capital,
        FIRST_VALUE(invested_capital) OVER (
            PARTITION BY symbol
            ORDER BY CAST(report_date AS DATE)
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS beginning_invested_capital
    FROM quarterly_data
),

ttm_roic_data AS (
    SELECT
        symbol,
        report_date,
        ttm_nopat,
        (beginning_invested_capital + ending_invested_capital) / 2.0 AS ttm_avg_invested_capital
    FROM ttm_window
    WHERE quarter_count = 4 AND id_range = 3
)

SELECT *
FROM ttm_roic_data
PIVOT (
    ANY_VALUE(ttm_nopat) AS ttm_nopat,
    ANY_VALUE(ttm_avg_invested_capital) AS ttm_avg_invested_capital
    FOR symbol IN ({symbols})
)
ORDER BY report_date;

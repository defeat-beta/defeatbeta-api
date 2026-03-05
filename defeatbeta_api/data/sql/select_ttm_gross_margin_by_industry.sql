WITH raw_data AS (
    SELECT
        symbol,
        report_date,
        MAX(CASE WHEN item_name = 'gross_profit' THEN item_value END) AS gross_profit,
        MAX(CASE WHEN item_name = 'total_revenue' THEN item_value END) AS total_revenue
    FROM
        '{stock_statement}'
    WHERE
        symbol in ({symbols})
        AND item_name IN ('gross_profit', 'total_revenue')
        AND period_type = 'quarterly'
        AND report_date != 'TTM'
        AND finance_type = 'income_statement'
    GROUP BY symbol, report_date
),
quarterly_data AS (
    SELECT
        symbol,
        report_date,
        gross_profit,
        total_revenue,
        YEAR(report_date::DATE) * 4 + QUARTER(report_date::DATE) AS continuous_id
    FROM raw_data
    WHERE gross_profit IS NOT NULL AND total_revenue IS NOT NULL
),
ttm_window AS (
    SELECT
        symbol,
        report_date,
        SUM(gross_profit) OVER (
            PARTITION BY symbol
            ORDER BY CAST(report_date AS DATE)
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS ttm_gross_profit,
        SUM(total_revenue) OVER (
            PARTITION BY symbol
            ORDER BY CAST(report_date AS DATE)
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS ttm_revenue,
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
        ) AS id_range
    FROM quarterly_data
),
ttm_gross_margin_data AS (
    SELECT
        symbol,
        report_date,
        ttm_gross_profit,
        ttm_revenue
    FROM ttm_window
    WHERE quarter_count = 4 AND id_range = 3
)
SELECT *
FROM ttm_gross_margin_data
PIVOT (
    ANY_VALUE(ttm_gross_profit) AS ttm_gross_profit,
    ANY_VALUE(ttm_revenue) AS ttm_revenue
    FOR symbol IN ({symbols})
)
ORDER BY report_date;

WITH raw_data AS (
    SELECT
        symbol,
        report_date,
        MAX(CASE WHEN item_name = 'net_income_common_stockholders' THEN item_value END) AS net_income,
        MAX(CASE WHEN item_name = 'total_assets' THEN item_value END) AS total_assets
    FROM
        '{stock_statement}'
    WHERE
        symbol in ({symbols})
        AND item_name IN ('net_income_common_stockholders', 'total_assets')
        AND period_type = 'quarterly'
        AND report_date != 'TTM'
        AND finance_type IN ('income_statement', 'balance_sheet')
    GROUP BY symbol, report_date
),
quarterly_data AS (
    SELECT
        symbol,
        report_date,
        net_income,
        total_assets,
        YEAR(report_date::DATE) * 4 + QUARTER(report_date::DATE) AS continuous_id
    FROM raw_data
    WHERE net_income IS NOT NULL AND total_assets IS NOT NULL
),
ttm_window AS (
    SELECT
        symbol,
        report_date,
        SUM(net_income) OVER (
            PARTITION BY symbol
            ORDER BY CAST(report_date AS DATE)
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS ttm_net_income,
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
        -- ttm_avg_assets: average of assets at start and end of the TTM window
        total_assets AS ending_assets,
        FIRST_VALUE(total_assets) OVER (
            PARTITION BY symbol
            ORDER BY CAST(report_date AS DATE)
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS beginning_assets
    FROM quarterly_data
),
ttm_roa_data AS (
    SELECT
        symbol,
        report_date,
        ttm_net_income,
        (beginning_assets + ending_assets) / 2.0 AS ttm_avg_assets
    FROM ttm_window
    WHERE quarter_count = 4 AND id_range = 3
)
SELECT *
FROM ttm_roa_data
PIVOT (
    ANY_VALUE(ttm_net_income) AS ttm_net_income,
    ANY_VALUE(ttm_avg_assets) AS ttm_avg_assets
    FOR symbol IN ({symbols})
)
ORDER BY report_date;

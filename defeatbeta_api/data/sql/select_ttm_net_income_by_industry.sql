WITH quarterly_data AS (
    SELECT
        symbol,
        report_date,
        item_value,
        YEAR(report_date::DATE) * 4 + QUARTER(report_date::DATE) AS continuous_id
    FROM
        '{stock_statement}'
    WHERE
        symbol in ({symbols})
        AND item_name = 'net_income_common_stockholders'
        AND period_type = 'quarterly'
        AND item_value IS NOT NULL
        AND report_date != 'TTM'
),
sliding_window AS (
    SELECT
        symbol,
        report_date,
        ttm_net_income
    FROM (
        SELECT
            symbol,
            report_date,
            SUM(item_value) OVER (
                PARTITION BY symbol
                ORDER BY CAST(report_date AS DATE)
                ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
            ) AS ttm_net_income,
            COUNT(*) OVER (
                PARTITION BY symbol
                ORDER BY CAST(report_date AS DATE)
                ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
            ) AS quarter_count,
            -- Ensure the 4 quarters in the window are truly consecutive:
            -- max continuous_id - min continuous_id must equal 3
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
    ) t
    WHERE quarter_count = 4 AND id_range = 3
)
SELECT *
    FROM sliding_window
    PIVOT (
        ANY_VALUE(ttm_net_income)
        FOR symbol IN ({symbols})
    ) order by report_date

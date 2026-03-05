WITH quarterly_data AS (
    SELECT
        symbol,
        report_date,
        item_name,
        item_value,
        finance_type,
        period_type,
        YEAR(report_date::DATE) * 4 + QUARTER(report_date::DATE) AS continuous_id
    FROM
        '{ttm_ebitda_url}'
    WHERE
        symbol = '{ticker}'
        AND item_name = 'ebitda'
        AND period_type = 'quarterly'
        AND item_value IS NOT NULL
        AND report_date != 'TTM'
),
sliding_window AS (
    SELECT
    report_date,
    ttm_ebitda,
    TO_JSON(MAP(window_report_dates, window_item_values)) AS report_date_2_ebitda
    FROM (
        SELECT
            symbol,
            report_date,
            item_name,
            item_value,
            finance_type,
            period_type,
            SUM(item_value) OVER (
                PARTITION BY symbol
                ORDER BY CAST(report_date AS DATE)
                ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
            ) AS ttm_ebitda,
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
            ) AS id_range,
            ARRAY_AGG(report_date) OVER (
                PARTITION BY symbol
                ORDER BY CAST(report_date AS DATE)
                ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
            ) AS window_report_dates,
            ARRAY_AGG(item_value) OVER (
                PARTITION BY symbol
                ORDER BY CAST(report_date AS DATE)
                ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
            ) AS window_item_values
        FROM quarterly_data
    ) t
    WHERE quarter_count = 4 AND id_range = 3
)
SELECT
    * from sliding_window

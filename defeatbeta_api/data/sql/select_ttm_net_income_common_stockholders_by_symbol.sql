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
        '{ttm_net_income_url}'
    WHERE
        symbol = '{ticker}'
        AND item_name = 'net_income_common_stockholders'
        AND period_type = 'quarterly'
        AND item_value IS NOT NULL
        AND report_date != 'TTM'
),
quarterly_data_rn AS (
    SELECT
        symbol,
        report_date,
        item_name,
        item_value,
        finance_type,
        period_type,
        continuous_id,
        ROW_NUMBER() OVER (ORDER BY continuous_id ASC) AS rn_asc
    FROM
        quarterly_data
),
grouped_data AS (
    SELECT
        *,
        continuous_id - rn_asc AS group_id
    FROM
        quarterly_data_rn
),
base_data_window AS (
    SELECT
        symbol,
        report_date,
        item_name,
        item_value,
        finance_type,
        period_type
    FROM
        grouped_data t1
        where t1.group_id = (
            SELECT
                group_id
            FROM
                grouped_data
            ORDER BY
                continuous_id DESC
                LIMIT 1
        )
    ORDER BY
        continuous_id ASC
),
sliding_window AS (
    SELECT
    report_date,
    ttm_net_income,
    TO_JSON(MAP(window_report_dates, window_item_values)) AS report_date_2_net_income,
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
            ) AS ttm_net_income,
            COUNT(*) OVER (
                PARTITION BY symbol
                ORDER BY CAST(report_date AS DATE)
                ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
            ) AS quarter_count,
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
        FROM base_data_window
    ) t
    WHERE quarter_count = 4
)
SELECT
    * from sliding_window

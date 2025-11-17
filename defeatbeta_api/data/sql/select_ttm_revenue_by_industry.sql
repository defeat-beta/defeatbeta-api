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
        '{stock_statement}'
    WHERE
        symbol in ({symbols})
        AND item_name = 'total_revenue'
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
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY continuous_id ASC) AS rn_asc
    FROM
        quarterly_data ORDER BY symbol, rn_asc
),
grouped_data AS (
    SELECT
        *,
        continuous_id - rn_asc AS group_id
    FROM
        quarterly_data_rn
),
base_data_window AS (
    SELECT *
    FROM (
        SELECT
            *,
            MAX(group_id) OVER (PARTITION BY symbol) AS max_group_id
        FROM grouped_data
    ) t
    WHERE group_id = max_group_id
),
sliding_window AS (
    SELECT
        symbol,
        report_date,
        ttm_revenue
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
            ) AS ttm_revenue,
            COUNT(*) OVER (
                PARTITION BY symbol
                ORDER BY CAST(report_date AS DATE)
                ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
            ) AS quarter_count
        FROM base_data_window
    ) t
    WHERE quarter_count = 4
)
SELECT *
    FROM sliding_window
    PIVOT (
        ANY_VALUE(ttm_revenue)
        FOR symbol IN ({symbols})
    ) order by report_date
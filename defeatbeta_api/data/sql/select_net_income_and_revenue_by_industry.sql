WITH netincome_revenue_table AS (
            SELECT
                symbol,
                report_date,
                MAX(CASE WHEN item_name = 'net_income_common_stockholders' THEN item_value END) AS net_income_common_stockholders,
                MAX(CASE WHEN item_name = 'total_revenue' THEN item_value END) AS total_revenue
            FROM
                '{stock_statement}'
            WHERE
                symbol in ({symbols})
                AND item_name IN ('net_income_common_stockholders', 'total_revenue')
                AND report_date != 'TTM'
                AND period_type = 'quarterly'
                AND finance_type in ('income_statement')
            GROUP BY symbol, report_date
),

base_data AS (
    SELECT
        symbol,
        report_date,
        net_income_common_stockholders,
        total_revenue,
        YEAR(report_date::DATE) AS report_year,
        QUARTER(report_date::DATE) AS report_quarter,
        YEAR(report_date::DATE) * 4 + QUARTER(report_date::DATE) AS continuous_id
    FROM
        netincome_revenue_table
    WHERE
        net_income_common_stockholders IS NOT NULL AND total_revenue IS NOT NULL
),

base_data_rn AS (
    SELECT
        symbol,
        report_date,
        net_income_common_stockholders,
        total_revenue,
        report_year,
        report_quarter,
        continuous_id,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY continuous_id ASC) AS rn_asc
    FROM
        base_data
),

grouped_data AS (
    SELECT
        *,
        continuous_id - rn_asc AS group_id
    FROM
        base_data_rn
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

net_incomet_and_revenue AS (
    SELECT
        symbol,
        report_date,
        net_income_common_stockholders,
        total_revenue
    FROM base_data_window
),

pivoted AS (
    SELECT *
    FROM net_incomet_and_revenue
    PIVOT (
        ANY_VALUE(net_income_common_stockholders) AS net_income_common_stockholders,
        ANY_VALUE(total_revenue) AS revenue
        FOR symbol IN ({symbols})
    )
)
SELECT
    *
FROM pivoted
ORDER BY report_date;
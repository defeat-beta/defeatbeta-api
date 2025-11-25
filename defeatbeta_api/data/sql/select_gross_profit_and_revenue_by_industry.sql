WITH gross_profit_revenue_table AS (
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
                AND report_date != 'TTM'
                AND period_type = 'quarterly'
                AND finance_type in ('income_statement')
            GROUP BY symbol, report_date
),

gross_profit_and_revenue AS (
    SELECT
        symbol,
        report_date,
        gross_profit,
        total_revenue
    FROM gross_profit_revenue_table
),

pivoted AS (
    SELECT *
    FROM gross_profit_and_revenue
    PIVOT (
        ANY_VALUE(gross_profit) AS gross_profit,
        ANY_VALUE(total_revenue) AS revenue
        FOR symbol IN ({symbols})
    )
)
SELECT
    *
FROM pivoted
ORDER BY report_date;
WITH ebitda_revenue_table AS (
            SELECT
                symbol,
                report_date,
                MAX(CASE WHEN item_name = 'ebitda' THEN item_value END) AS ebitda,
                MAX(CASE WHEN item_name = 'total_revenue' THEN item_value END) AS total_revenue
            FROM
                {stock_statement_url}
            WHERE
                symbol in ({symbols})
                AND item_name IN ('ebitda', 'total_revenue')
                AND report_date != 'TTM'
                AND period_type = 'quarterly'
                AND finance_type in ('income_statement')
            GROUP BY symbol, report_date
),

ebitda_and_revenue AS (
    SELECT
        symbol,
        report_date,
        ebitda,
        total_revenue
    FROM ebitda_revenue_table
),

pivoted AS (
    SELECT *
    FROM ebitda_and_revenue
    PIVOT (
        ANY_VALUE(ebitda) AS ebitda,
        ANY_VALUE(total_revenue) AS revenue
        FOR symbol IN ({symbols})
    )
)
SELECT
    *
FROM pivoted
ORDER BY report_date;
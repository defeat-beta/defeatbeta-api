WITH netincome_revenue_table AS (
            SELECT
                symbol,
                report_date,
                MAX(CASE WHEN item_name = 'net_income_common_stockholders' THEN item_value END) AS net_income_common_stockholders,
                MAX(CASE WHEN item_name = 'total_revenue' THEN item_value END) AS total_revenue
            FROM
                {stock_statement_url}
            WHERE
                symbol in ({symbols})
                AND item_name IN ('net_income_common_stockholders', 'total_revenue')
                AND report_date != 'TTM'
                AND period_type = 'quarterly'
                AND finance_type in ('income_statement')
            GROUP BY symbol, report_date
),

net_incomet_and_revenue AS (
    SELECT
        symbol,
        report_date,
        net_income_common_stockholders,
        total_revenue
    FROM netincome_revenue_table
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
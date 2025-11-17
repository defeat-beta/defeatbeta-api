WITH quarterly_data AS (
    SELECT
        symbol,
        report_date,
        item_value as bve
    FROM
        '{stock_statement}'
    WHERE
        symbol in ({symbols})
        AND item_name = 'stockholders_equity'
        AND period_type = 'quarterly'
        AND item_value IS NOT NULL
        AND report_date != 'TTM'
)
SELECT *
    FROM quarterly_data
    PIVOT (
        ANY_VALUE(bve)
        FOR symbol in ({symbols})
    ) order by report_date
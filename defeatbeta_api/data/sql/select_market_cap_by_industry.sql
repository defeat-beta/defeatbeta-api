WITH market_cap_table AS (
    SELECT
        p.symbol,
        p.report_date,
        ROUND(p.close * s.shares_outstanding, 2) AS market_capitalization
    FROM
        read_parquet('{stock_prices}') AS p
    LEFT JOIN
        read_parquet('{stock_shares_outstanding}') AS s
        ON p.symbol = s.symbol
        AND p.report_date >= s.report_date
    WHERE
        p.symbol IN ({symbols})
)
SELECT *
    FROM market_cap_table
    PIVOT (
        ANY_VALUE(market_capitalization)
        FOR symbol IN ({symbols})
    ) order by report_date
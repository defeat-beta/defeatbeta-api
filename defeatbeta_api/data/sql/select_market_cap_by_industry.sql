WITH market_cap_table AS (
    SELECT
        p.symbol,
        p.report_date,
        ROUND(p.close * s.shares_outstanding, 2) AS market_capitalization
    FROM
        {stock_prices_url} AS p
    LEFT JOIN
        {stock_shares_outstanding_url} AS s
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
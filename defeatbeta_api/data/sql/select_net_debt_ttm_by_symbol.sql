WITH net_debt_base AS (
    SELECT
        symbol,
        report_date,
        MAX(CASE WHEN item_name = 'long_term_debt_and_capital_lease_obligation' THEN item_value END) AS long_term_debt,
        MAX(CASE WHEN item_name = 'cash_cash_equivalents_and_short_term_investments' THEN item_value END) AS cash_and_short_term_investments
    FROM
        '{url}'
    WHERE
        symbol = '{ticker}'
        AND item_name IN ('long_term_debt_and_capital_lease_obligation', 'cash_cash_equivalents_and_short_term_investments')
        AND period_type = 'quarterly'
        AND report_date != 'TTM'
        AND finance_type = 'balance_sheet'
    GROUP BY symbol, report_date
    HAVING long_term_debt IS NOT NULL OR cash_and_short_term_investments IS NOT NULL
),

net_debt_calc AS (
    SELECT
        symbol,
        report_date,
        long_term_debt,
        cash_and_short_term_investments,
        COALESCE(long_term_debt, 0) - COALESCE(cash_and_short_term_investments, 0) AS net_debt
    FROM net_debt_base
),

net_debt_ttm AS (
    SELECT
        symbol,
        report_date,
        long_term_debt,
        cash_and_short_term_investments,
        net_debt,
        AVG(net_debt) OVER (
            PARTITION BY symbol
            ORDER BY report_date::DATE
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS avg_net_debt_ttm,
        COUNT(*) OVER (
            PARTITION BY symbol
            ORDER BY report_date::DATE
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS quarters_in_window
    FROM net_debt_calc
)

SELECT
    symbol,
    report_date,
    long_term_debt,
    cash_and_short_term_investments,
    net_debt,
    CASE WHEN quarters_in_window = 4 THEN ROUND(avg_net_debt_ttm, 0) ELSE NULL END AS avg_net_debt_ttm
FROM net_debt_ttm
ORDER BY report_date

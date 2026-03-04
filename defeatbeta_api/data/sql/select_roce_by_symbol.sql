WITH roce_table AS (
    SELECT
        symbol,
        report_date,
        MAX(CASE WHEN item_name = 'ebit' THEN item_value END) AS ebit,
        MAX(CASE WHEN item_name = 'total_assets' THEN item_value END) AS total_assets,
        MAX(CASE WHEN item_name = 'current_liabilities' THEN item_value END) AS current_liabilities
    FROM
        '{url}'
    WHERE
        symbol = '{ticker}'
        AND item_name IN ('ebit', 'total_assets', 'current_liabilities')
        AND report_date != 'TTM'
        AND period_type = 'quarterly'
        AND finance_type IN ('income_statement', 'balance_sheet')
    GROUP BY symbol, report_date
),

base_data AS (
    SELECT
        symbol,
        report_date,
        ebit,
        total_assets - current_liabilities AS capital_employed,
        YEAR(report_date::DATE) * 4 + QUARTER(report_date::DATE) AS continuous_id
    FROM
        roce_table
    WHERE
        ebit IS NOT NULL AND total_assets IS NOT NULL AND current_liabilities IS NOT NULL
),

base_data_rn AS (
    SELECT
        *,
        ROW_NUMBER() OVER (ORDER BY continuous_id ASC) AS rn_asc
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
    SELECT
        symbol,
        report_date,
        ebit,
        capital_employed,
        ROW_NUMBER() OVER (ORDER BY report_date ASC) AS rn
    FROM
        grouped_data t1
        JOIN (
            SELECT group_id
            FROM grouped_data
            ORDER BY continuous_id DESC
            LIMIT 1
        ) t2
        ON t1.group_id = t2.group_id
    ORDER BY continuous_id ASC
),

capital_employed_with_lag AS (
    SELECT
        symbol,
        report_date,
        ebit,
        capital_employed AS ending_capital_employed,
        LAG(capital_employed, 1) OVER (PARTITION BY symbol ORDER BY report_date) AS beginning_capital_employed
    FROM base_data_window
),

capital_employed_avg AS (
    SELECT
        symbol,
        report_date,
        ebit,
        ending_capital_employed,
        beginning_capital_employed,
        (beginning_capital_employed + ending_capital_employed) / 2.0 AS avg_capital_employed
    FROM capital_employed_with_lag
    WHERE beginning_capital_employed IS NOT NULL
)

SELECT
    symbol,
    report_date,
    ebit,
    beginning_capital_employed,
    ending_capital_employed,
    avg_capital_employed,
    ROUND(
        CASE
            WHEN ebit < 0 OR avg_capital_employed < 0 THEN
                -ABS(ebit / avg_capital_employed)
            ELSE
                ebit / avg_capital_employed
        END
    , 4) AS roce
FROM capital_employed_avg
ORDER BY report_date;

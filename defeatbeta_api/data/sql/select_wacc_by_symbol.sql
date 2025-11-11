WITH wacc_table AS (
    SELECT
        symbol,
        report_date,
        MAX(CASE WHEN item_name = 'total_debt' THEN item_value END) AS total_debt,
        MAX(CASE WHEN item_name = 'interest_expense' THEN item_value END) AS interest_expense,
        MAX(CASE WHEN item_name = 'pretax_income' THEN item_value END) AS pretax_income,
        MAX(CASE WHEN item_name = 'tax_provision' THEN item_value END) AS tax_provision,
        MAX(CASE WHEN item_name = 'tax_rate_for_calcs' THEN item_value END) AS tax_rate_for_calcs
    FROM
        '{url}'
    WHERE
        symbol = '{ticker}'
        AND item_name IN ('total_debt', 'interest_expense', 'pretax_income', 'tax_provision', 'tax_rate_for_calcs')
        AND report_date != 'TTM'
        AND period_type = 'quarterly'
        AND finance_type in ('income_statement', 'balance_sheet')
    GROUP BY symbol, report_date
),

base_data AS (
    SELECT
        symbol,
        report_date,
        total_debt,
        interest_expense,
        pretax_income,
        tax_provision,
        tax_rate_for_calcs,
        YEAR(report_date::DATE) AS report_year,
        QUARTER(report_date::DATE) AS report_quarter,
        YEAR(report_date::DATE) * 4 + QUARTER(report_date::DATE) AS continuous_id
    FROM
        wacc_table
    WHERE
        total_debt IS NOT NULL AND interest_expense IS NOT NULL AND pretax_income IS NOT NULL AND tax_provision IS NOT NULL AND tax_rate_for_calcs IS NOT NULL
),

base_data_rn AS (
    SELECT
        symbol,
        report_date,
        total_debt,
        interest_expense,
        pretax_income,
        tax_provision,
        tax_rate_for_calcs,
        report_year,
        report_quarter,
        continuous_id,
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
        total_debt,
        interest_expense,
        pretax_income,
        tax_provision,
        tax_rate_for_calcs,
        ROW_NUMBER() OVER (ORDER BY report_date ASC) AS rn
    FROM
        grouped_data t1
        JOIN (
            SELECT
                group_id
            FROM
                grouped_data
            ORDER BY
                continuous_id DESC
                LIMIT 1
        ) t2
    ON t1.group_id = t2.group_id
    ORDER BY
        continuous_id ASC
)

select
    symbol,
    report_date,
    total_debt,
    interest_expense,
    pretax_income,
    tax_provision,
    tax_rate_for_calcs
from base_data_window
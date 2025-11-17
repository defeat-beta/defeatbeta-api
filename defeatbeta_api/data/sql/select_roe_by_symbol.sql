WITH roe_table AS (
            SELECT
                symbol,
                report_date,
                MAX(CASE WHEN item_name = 'net_income_common_stockholders' THEN item_value END) AS net_income_common_stockholders,
                MAX(CASE WHEN item_name = 'stockholders_equity' THEN item_value END) AS stockholders_equity
            FROM
                '{url}'
            WHERE
                symbol = '{ticker}'
                AND item_name IN ('net_income_common_stockholders', 'stockholders_equity')
                AND report_date != 'TTM'
                AND period_type = 'quarterly'
                AND finance_type in ('income_statement', 'balance_sheet')
            GROUP BY symbol, report_date
),

base_data AS (
    SELECT
        symbol,
        report_date,
        net_income_common_stockholders,
        stockholders_equity,
        YEAR(report_date::DATE) AS report_year,
        QUARTER(report_date::DATE) AS report_quarter,
        YEAR(report_date::DATE) * 4 + QUARTER(report_date::DATE) AS continuous_id
    FROM
        roe_table
    WHERE
        net_income_common_stockholders IS NOT NULL AND stockholders_equity IS NOT NULL
),

base_data_rn AS (
    SELECT
        symbol,
        report_date,
        net_income_common_stockholders,
        stockholders_equity,
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
        net_income_common_stockholders,
        stockholders_equity,
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
),

equity_with_lag AS (
    SELECT
        symbol,
        report_date,
        net_income_common_stockholders,
        stockholders_equity as ending_stockholders_equity,
        LAG(stockholders_equity, 1) OVER (PARTITION BY symbol ORDER BY report_date) AS beginning_stockholders_equity
    FROM base_data_window
),

equity_avg AS (
    SELECT
        symbol,
        report_date,
        net_income_common_stockholders,
        ending_stockholders_equity,
        beginning_stockholders_equity,
        (beginning_stockholders_equity + ending_stockholders_equity) / 2.0 AS avg_equity
    FROM equity_with_lag
    WHERE beginning_stockholders_equity IS NOT NULL
)

select symbol,
        report_date,
        net_income_common_stockholders,
        beginning_stockholders_equity,
        ending_stockholders_equity,
        avg_equity,
        ROUND(
            CASE
                WHEN net_income_common_stockholders < 0 OR avg_equity < 0 THEN
                    -ABS(net_income_common_stockholders / avg_equity)
                ELSE
                    net_income_common_stockholders / avg_equity
            END
        , 4) AS roe
    from equity_avg order by report_date;

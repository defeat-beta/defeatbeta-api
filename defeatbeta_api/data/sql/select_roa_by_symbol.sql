WITH roe_table AS (
            SELECT
                symbol,
                report_date,
                MAX(CASE WHEN item_name = 'net_income_common_stockholders' THEN item_value END) AS net_income_common_stockholders,
                MAX(CASE WHEN item_name = 'total_assets' THEN item_value END) AS total_assets
            FROM
                '{url}'
            WHERE
                symbol = '{ticker}'
                AND item_name IN ('net_income_common_stockholders', 'total_assets')
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
        total_assets,
        YEAR(report_date::DATE) AS report_year,
        QUARTER(report_date::DATE) AS report_quarter,
        YEAR(report_date::DATE) * 4 + QUARTER(report_date::DATE) AS continuous_id
    FROM
        roe_table
    WHERE
        net_income_common_stockholders IS NOT NULL AND total_assets IS NOT NULL
),

base_data_rn AS (
    SELECT
        symbol,
        report_date,
        net_income_common_stockholders,
        total_assets,
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
        total_assets,
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

assets_with_lag AS (
    SELECT
        symbol,
        report_date,
        net_income_common_stockholders,
        total_assets as ending_total_assets,
        LAG(total_assets, 1) OVER (PARTITION BY symbol ORDER BY report_date) AS beginning_total_assets
    FROM base_data_window
),

asserts_avg AS (
    SELECT
        symbol,
        report_date,
        net_income_common_stockholders,
        ending_total_assets,
        beginning_total_assets,
        (beginning_total_assets + ending_total_assets) / 2.0 AS avg_assets
    FROM assets_with_lag
    WHERE beginning_total_assets IS NOT NULL
)

select symbol,
        report_date,
        net_income_common_stockholders,
        beginning_total_assets,
        ending_total_assets,
        avg_assets,
        round(net_income_common_stockholders / avg_assets, 4) AS roa
    from asserts_avg order by report_date;

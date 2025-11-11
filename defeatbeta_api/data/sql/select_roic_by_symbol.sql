WITH roic_table AS (
 SELECT
     symbol,
     report_date,
     MAX(CASE WHEN item_name = 'ebit' THEN item_value END) AS ebit,
     MAX(CASE WHEN item_name = 'tax_rate_for_calcs' THEN item_value END) AS tax_rate_for_calcs,
     MAX(CASE WHEN item_name = 'invested_capital' THEN item_value END) AS invested_capital
 FROM
     '{url}'
 WHERE
     symbol = '{ticker}'
     AND item_name IN ('ebit', 'tax_rate_for_calcs', 'net_income_common_stockholders', 'invested_capital')
     AND report_date != 'TTM'
     AND period_type = 'quarterly'
     AND finance_type in ('income_statement', 'balance_sheet')
 GROUP BY symbol, report_date
),

base_data AS (
  SELECT
      symbol,
      report_date,
      ebit,
      tax_rate_for_calcs,
      ebit * (1 - tax_rate_for_calcs) as nopat,
      invested_capital,
      YEAR(report_date::DATE) AS report_year,
      QUARTER(report_date::DATE) AS report_quarter,
      YEAR(report_date::DATE) * 4 + QUARTER(report_date::DATE) AS continuous_id
  FROM
      roic_table
),

base_data_rn AS (
  SELECT
      symbol,
      report_date,
      ebit,
      tax_rate_for_calcs,
      nopat,
      invested_capital,
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
      ebit,
      tax_rate_for_calcs,
      nopat,
      invested_capital,
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

invested_capital_with_lag AS (
  SELECT
      symbol,
      report_date,
      ebit,
      tax_rate_for_calcs,
      nopat,
      invested_capital as ending_invested_capital,
      LAG(invested_capital, 1) OVER (PARTITION BY symbol ORDER BY report_date) AS beginning_invested_capital
  FROM base_data_window
),

invested_capital_avg AS (
  SELECT
      symbol,
      report_date,
      ebit,
      tax_rate_for_calcs,
      nopat,
      ending_invested_capital,
      beginning_invested_capital,
      (beginning_invested_capital + ending_invested_capital) / 2.0 AS avg_invested_capital
  FROM invested_capital_with_lag
  WHERE beginning_invested_capital IS NOT NULL
)


select symbol,
      report_date,
      ebit,
      tax_rate_for_calcs,
      nopat,
      beginning_invested_capital,
      ending_invested_capital,
      avg_invested_capital,
      round(nopat / avg_invested_capital, 4) AS roic
  from invested_capital_avg order by report_date;
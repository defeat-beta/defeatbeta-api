SELECT symbol,
       report_date,
       {numerator_item},
       total_revenue,
       round({numerator_item}/total_revenue, 4) as {margin_column}
FROM (
    SELECT
         symbol,
         report_date,
         MAX(CASE WHEN t1.item_name = '{numerator_item}' THEN t1.item_value END) AS {numerator_item},
         MAX(CASE WHEN t1.item_name = 'total_revenue' THEN t1.item_value END) AS total_revenue
      FROM '{url}' t1
      WHERE symbol = '{ticker}'
        {finance_type_filter}
        {ttm_filter}
        AND item_name IN ('{numerator_item}', 'total_revenue')
        AND period_type = '{period_type}'
      GROUP BY symbol, report_date
) t
ORDER BY report_date ASC
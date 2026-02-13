SELECT
    p1.report_date,
    p1.close AS stock_close,
    p2.close AS benchmark_close
FROM '{url}' p1
INNER JOIN '{url}' p2
    ON p1.report_date = p2.report_date
WHERE p1.symbol = '{ticker}'
    AND p2.symbol = '{benchmark}'
    AND p1.report_date >= '{start_date}'
    AND p1.report_date <= '{end_date}'
ORDER BY p1.report_date

SELECT symbol, fiscal_year, fiscal_quarter, report_date
FROM '{url}'
WHERE symbol = '{ticker}'
ORDER BY fiscal_year, fiscal_quarter

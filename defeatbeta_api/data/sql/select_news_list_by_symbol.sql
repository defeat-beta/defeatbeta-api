SELECT uuid, symbol, title, publisher, report_date, type, link
FROM '{url}'
WHERE symbol = '{ticker}'
ORDER BY report_date ASC

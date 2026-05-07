SELECT uuid, related_symbols, title, publisher, report_date, type, link
FROM '{url}'
WHERE related_symbols = '{ticker}'
ORDER BY report_date ASC

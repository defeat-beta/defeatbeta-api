SELECT DISTINCT
    b.symbol,
    b.report_date,
    b.period_label,
    b.table_name AS breakdown_type,
    mb.member_name AS item_name,
    it.value AS item_value
FROM '{url}' b,
    LATERAL (SELECT unnest(b.items)) AS t1(it),
    LATERAL (SELECT unnest(it.members)) AS t2(mb)
WHERE b.symbol = '{ticker}'
ORDER BY b.report_date,b.period_label,b.table_name,it.value ASC, b.table_name, mb.member_name

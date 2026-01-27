SELECT
    idx,
    info.ticker as symbol,
    info.cik_str as cik,
    info.title as name,
    info.financial_currency as financial_currency
FROM (
    SELECT unnest(map_keys(data)) as idx, unnest(map_values(data)) as info
    FROM read_json('{url}',
                   columns={{data: 'MAP(VARCHAR, STRUCT(cik_str INTEGER, ticker VARCHAR, title VARCHAR, financial_currency VARCHAR))'}})
) WHERE symbol = '{symbol}'

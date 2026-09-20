SELECT
    idx,
    info.ticker as symbol,
    info.{identifier_field} as {identifier_alias},
    info.title as name,
    info.financial_currency as financial_currency
FROM (
    SELECT unnest(map_keys(data)) as idx, unnest(map_values(data)) as info
    FROM read_json('{url}',
                   columns={{data: 'MAP(VARCHAR, STRUCT({identifier_field} {identifier_type}, ticker VARCHAR, title VARCHAR, financial_currency VARCHAR))'}})
) WHERE symbol = '{symbol}'

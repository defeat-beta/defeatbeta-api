SELECT
    UNNEST(transcripts).paragraph_number AS paragraph_number,
    UNNEST(transcripts).speaker          AS speaker,
    UNNEST(transcripts).content          AS content
FROM '{url}'
WHERE symbol = '{ticker}'
  AND fiscal_year    = {fiscal_year}
  AND fiscal_quarter = {fiscal_quarter}
ORDER BY paragraph_number

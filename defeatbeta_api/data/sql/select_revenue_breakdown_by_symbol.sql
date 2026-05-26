WITH RECURSIVE
raw AS (
    SELECT *
    FROM '{url}'
    WHERE symbol = '{ticker}'
),
flat_items AS (
    SELECT DISTINCT
        r.symbol,
        r.report_date,
        r.period_label,
        r.form_type,
        r.table_name          AS breakdown_type,
        mb.axis_qname,
        mb.member_qname,
        mb.member_name        AS item_name,
        it.value              AS item_value
    FROM raw r,
        LATERAL (SELECT unnest(r.items))     AS t1(it),
        LATERAL (SELECT unnest(it.members))  AS t2(mb)
),
flat_hierarchy AS (
    SELECT DISTINCT
        r.symbol,
        r.report_date,
        r.period_label,
        r.table_name          AS breakdown_type,
        mh.axis_qname,
        n.qname,
        n.parent_qname,
        n.parent_name,
        n.depth,
        n."order"             AS member_order
    FROM raw r,
        LATERAL (SELECT unnest(r.member_hierarchy))  AS t1(mh),
        LATERAL (SELECT unnest(mh.nodes))            AS t2(n)
),
hierarchy_with_path AS (
    SELECT
        symbol, report_date, period_label, breakdown_type,
        axis_qname, qname, parent_qname, parent_name,
        depth, member_order,
        printf('%020.4f', member_order) AS sort_path
    FROM flat_hierarchy
    WHERE depth = 1

    UNION ALL

    SELECT
        fh.symbol, fh.report_date, fh.period_label, fh.breakdown_type,
        fh.axis_qname, fh.qname, fh.parent_qname, fh.parent_name,
        fh.depth, fh.member_order,
        hp.sort_path || '|' || printf('%020.4f', fh.member_order) AS sort_path
    FROM flat_hierarchy fh
    JOIN hierarchy_with_path hp
        ON  fh.symbol         = hp.symbol
        AND fh.report_date    = hp.report_date
        AND fh.period_label   = hp.period_label
        AND fh.breakdown_type = hp.breakdown_type
        AND fh.axis_qname     = hp.axis_qname
        AND fh.parent_qname   = hp.qname
)
SELECT
    fi.symbol,
    fi.report_date,
    fi.period_label,
    fi.form_type,
    fi.breakdown_type,
    fi.item_name,
    fi.item_value,
    COALESCE(hwp.depth, 1)                                      AS depth,
    CASE WHEN hwp.depth = 1 THEN NULL ELSE hwp.parent_name END  AS parent_name
FROM flat_items fi
LEFT JOIN hierarchy_with_path hwp
    ON  fi.symbol         = hwp.symbol
    AND fi.report_date    = hwp.report_date
    AND fi.period_label   = hwp.period_label
    AND fi.breakdown_type = hwp.breakdown_type
    AND fi.axis_qname     = hwp.axis_qname
    AND fi.member_qname   = hwp.qname
ORDER BY
    fi.report_date,
    fi.period_label,
    fi.breakdown_type,
    COALESCE(hwp.sort_path, fi.item_name)

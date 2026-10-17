with obs as (
    select * from "price_analytics"."silver"."silver_price_observation"
),

names as (
    select
        product_key, product_name,
        row_number() over (
            partition by product_key
            order by case platform when 'Blibli' then 1 when 'Klik Indomaret' then 2 else 3 end,
                     crawled_at, raw_id
        ) as rn
    from obs
),

agg as (
    select
        product_key,
        max(match_key)                         as match_key,
        max(brand)                             as brand,
        max(category_from_breadcrumb)          as category,
        max(pack_qty_base)                     as pack_qty_base,
        max(pack_unit_base)                    as pack_unit_base,
        count(distinct platform)               as n_platforms,
        min(crawl_date)                        as first_seen_date
    from obs
    group by product_key
)

select
    a.product_key,
    n.product_name as canonical_name,
    a.brand,
    a.category,
    a.pack_qty_base,
    a.pack_unit_base,
    a.pack_qty_base::text || ' ' || a.pack_unit_base as pack_size,
    a.n_platforms,
    a.first_seen_date,
    a.match_key
from agg a
join names n on n.product_key = a.product_key and n.rn = 1
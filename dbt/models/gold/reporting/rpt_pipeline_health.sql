{#- Kesehatan data per platform: crawl terakhir, jumlah baris, dan status kesegaran.
    Ambang: <= 36 jam FRESH, <= 72 jam WARN, selebihnya STALE (sama dengan freshness di sumber raw). -#}
with agg as (
    select
        p.platform_name,
        max(f.last_crawled_at)           as last_crawled_at,
        max(f.price_date)                as latest_price_date,
        count(*)                         as fact_rows,
        count(distinct f.product_key)    as products_covered,
        count(distinct f.price_date)     as days_covered
    from {{ ref('fct_product_price_daily') }} f
    join {{ ref('dim_platform') }} p on p.platform_key = f.platform_key
    group by p.platform_name
)
select
    *,
    round((extract(epoch from (now() - last_crawled_at)) / 3600)::numeric, 1) as hours_since_last_crawl,
    case
        when now() - last_crawled_at <= interval '36 hours' then 'FRESH'
        when now() - last_crawled_at <= interval '72 hours' then 'WARN'
        else 'STALE'
    end as freshness_status
from agg

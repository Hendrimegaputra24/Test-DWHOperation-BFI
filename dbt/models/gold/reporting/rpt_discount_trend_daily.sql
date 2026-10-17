{#- Tren diskon harian per platform: seberapa banyak listing diskon dan seberapa dalam. -#}
select
    f.price_date,
    p.platform_name,
    count(*)                                                              as listings,
    count(*) filter (where f.is_discounted)                               as discounted_listings,
    round(100.0 * count(*) filter (where f.is_discounted) / count(*), 1)  as discount_frequency_pct,
    coalesce(round(avg(f.discount_pct) filter (where f.is_discounted), 1), 0) as avg_discount_depth_pct
from {{ ref('fct_product_price_daily') }} f
join {{ ref('dim_platform') }} p on p.platform_key = f.platform_key
group by f.price_date, p.platform_name

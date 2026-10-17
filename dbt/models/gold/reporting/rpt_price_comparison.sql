{#- Matriks perbandingan harga per produk: harga terakhir yang tersedia di tiap platform. -#}
with latest as (
    select
        f.*,
        row_number() over (partition by f.product_key, f.platform_key order by f.price_date desc) as rn
    from {{ ref('fct_product_price_daily') }} f
)
select
    m.product_name,
    m.brand,
    m.category,
    max(l.price_date)                                                          as as_of_date,
    max(l.price_idr) filter (where p.platform_name = 'Klik Indomaret')         as price_klik_indomaret,
    max(l.price_idr) filter (where p.platform_name = 'Blibli')                 as price_blibli,
    max(l.price_idr) filter (where p.platform_name = 'Tokopedia')              as price_tokopedia,
    min(l.price_idr)                                                           as min_price,
    max(l.price_idr)                                                           as max_price,
    round(100.0 * (max(l.price_idr) - min(l.price_idr)) / avg(l.price_idr), 1) as spread_pct,
    (array_agg(p.platform_name order by l.price_idr))[1]                       as cheapest_platform
from latest l
join {{ ref('dim_product_master') }} m on m.product_key = l.product_key
join {{ ref('dim_platform') }} p on p.platform_key = l.platform_key
where l.rn = 1
group by m.product_name, m.brand, m.category

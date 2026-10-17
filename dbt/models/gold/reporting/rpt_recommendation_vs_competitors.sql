{#- Rekomendasi terbaru per produk dibandingkan harga kompetitor di tanggal yang sama. -#}
with rec as (
    select distinct on (r.product_key) r.*
    from {{ ref('fct_price_recommendation') }} r
    order by r.product_key, r.date_key desc, r.run_ts desc
),
comp as (
    select
        f.date_key, f.product_key,
        max(f.price_idr) filter (where p.platform_name = 'Klik Indomaret') as price_klik_indomaret,
        max(f.price_idr) filter (where p.platform_name = 'Blibli')         as price_blibli,
        max(f.price_idr) filter (where p.platform_name = 'Tokopedia')      as price_tokopedia
    from {{ ref('fct_product_price_daily') }} f
    join {{ ref('dim_platform') }} p on p.platform_key = f.platform_key
    group by f.date_key, f.product_key
)
select
    m.product_name,
    m.category,
    d.date                                                  as recommendation_date,
    r.recommended_price_idr,
    r.competitor_median_price_idr,
    r.competitor_min_price_idr,
    c.price_klik_indomaret,
    c.price_blibli,
    c.price_tokopedia,
    r.price_floor_idr,
    round(100.0 * (r.recommended_price_idr - r.competitor_median_price_idr)
          / nullif(r.competitor_median_price_idr, 0), 1)    as gap_vs_median_pct,
    r.rule_applied,
    r.model_version,
    r.run_ts
from rec r
join {{ ref('dim_product_master') }} m on m.product_key = r.product_key
join {{ ref('dim_date') }} d on d.date_key = r.date_key
left join comp c on c.date_key = r.date_key and c.product_key = r.product_key

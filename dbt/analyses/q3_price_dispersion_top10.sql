-- Q3. Produk dengan sebaran harga terbesar antar platform (10 teratas).
-- Dasarnya rata-rata harga jual per platform selama periode data.
--   dispersion_pct = (rata-rata tertinggi - terendah) / rata-rata ketiganya * 100
with avg_by_platform as (
    select product_key, platform_key, avg(price_idr) as avg_price
    from gold.fct_product_price_daily
    group by 1, 2
),
spread as (
    select
        product_key,
        count(*)                                                     as n_platforms,
        min(avg_price)                                               as min_price,
        max(avg_price)                                               as max_price,
        avg(avg_price)                                               as mean_price,
        (array_agg(platform_key order by avg_price))[1]              as cheapest_platform_key,
        (array_agg(platform_key order by avg_price desc))[1]         as priciest_platform_key
    from avg_by_platform
    group by 1
    having count(*) >= 2
)
select
    m.product_name,
    m.category,
    s.n_platforms,
    round(s.min_price)                                               as min_avg_price_idr,
    round(s.max_price)                                               as max_avg_price_idr,
    round(100.0 * (s.max_price - s.min_price) / s.mean_price, 1)     as dispersion_pct,
    pc.platform_name                                                 as cheapest_platform,
    pe.platform_name                                                 as priciest_platform
from spread s
join gold.dim_product_master m using (product_key)
join gold.dim_platform pc on pc.platform_key = s.cheapest_platform_key
join gold.dim_platform pe on pe.platform_key = s.priciest_platform_key
order by dispersion_pct desc
limit 10;

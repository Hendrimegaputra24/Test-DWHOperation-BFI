-- Q1. Platform mana yang paling murah rata-rata untuk produk yang sebanding?
-- Sebanding = produk yang punya harga valid di SEMUA platform pada hari yang sama.
-- Indeks harga: harga platform dibagi rata-rata harga ketiga platform pada hari dan produk
-- yang sama, dikali 100. Di bawah 100 = lebih murah dari rata-rata. Dua versi:
--   price_index_actual = harga jual (sudah termasuk diskon)
--   price_index_list   = harga sebelum diskon (harga tercatat)
with full_days as (
    select price_date, product_key
    from gold.fct_product_price_daily
    group by 1, 2
    having count(distinct platform_key) = (select count(*) from gold.dim_platform)
),
base as (
    select
        f.platform_key,
        f.price_idr,
        f.original_price_idr,
        avg(f.price_idr)          over (partition by f.price_date, f.product_key) as avg_price_day,
        avg(f.original_price_idr) over (partition by f.price_date, f.product_key) as avg_list_day
    from gold.fct_product_price_daily f
    join full_days d using (price_date, product_key)
)
select
    p.platform_name,
    count(*)                                                   as comparable_observations,
    round(avg(b.price_idr / b.avg_price_day * 100), 1)          as price_index_actual,
    round(avg(b.original_price_idr / b.avg_list_day * 100), 1)  as price_index_list
from base b
join gold.dim_platform p using (platform_key)
group by 1
order by price_index_actual;

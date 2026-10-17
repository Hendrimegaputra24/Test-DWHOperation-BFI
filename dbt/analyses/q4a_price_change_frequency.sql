-- Q4a. Seberapa sering harga berubah? Per platform.
-- Perubahan dihitung antara dua hari berurutan (selisih tepat 1 hari) untuk listing yang sama.
--   price_change_rate_pct = harga jual berubah (termasuk awal/akhir promo)
--   list_change_rate_pct  = harga tercatat (sebelum diskon) berubah, yaitu kenaikan/penurunan permanen
with ordered as (
    select
        f.platform_key, f.price_date, f.price_idr, f.original_price_idr,
        lag(f.price_idr)          over w as prev_price,
        lag(f.original_price_idr) over w as prev_list,
        lag(f.price_date)         over w as prev_date
    from gold.fct_product_price_daily f
    window w as (partition by f.listing_key order by f.price_date)
),
pairs as (
    select * from ordered where prev_date is not null and price_date - prev_date = 1
)
select
    p.platform_name,
    count(*)                                                                     as day_pairs,
    count(*) filter (where price_idr <> prev_price)                              as price_changes,
    round(100.0 * count(*) filter (where price_idr <> prev_price) / count(*), 1) as price_change_rate_pct,
    count(*) filter (where original_price_idr <> prev_list)                      as list_price_changes,
    round(100.0 * count(*) filter (where original_price_idr <> prev_list) / count(*), 2) as list_change_rate_pct
from pairs
join gold.dim_platform p using (platform_key)
group by 1
order by price_change_rate_pct desc;

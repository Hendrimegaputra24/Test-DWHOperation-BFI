-- Q2. Seberapa dalam dan seberapa sering diskon, per kategori dan platform?
--   discount_frequency_pct = persen hari-observasi yang sedang diskon
--   avg_discount_depth_pct = rata-rata besar diskon, hanya pada hari yang diskon
select
    m.category,
    p.platform_name,
    count(*)                                                              as observation_days,
    count(*) filter (where f.is_discounted)                               as discounted_days,
    round(100.0 * count(*) filter (where f.is_discounted) / count(*), 1)  as discount_frequency_pct,
    round(avg(f.discount_pct) filter (where f.is_discounted), 1)          as avg_discount_depth_pct,
    max(f.discount_pct)                                                   as max_discount_pct
from gold.fct_product_price_daily f
join gold.dim_product_master m using (product_key)
join gold.dim_platform p using (platform_key)
group by 1, 2
order by 1, 2;

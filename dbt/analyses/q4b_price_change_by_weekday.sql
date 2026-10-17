-- Q4b. Pola perubahan harga menurut hari dalam minggu, per platform.
-- Hari = hari ketika harga baru terlihat (hari kedua dari pasangan hari berurutan).
with ordered as (
    select
        f.platform_key, f.price_date, f.price_idr,
        lag(f.price_idr) over w as prev_price,
        lag(f.price_date) over w as prev_date
    from gold.fct_product_price_daily f
    window w as (partition by f.listing_key order by f.price_date)
),
pairs as (
    select * from ordered where prev_date is not null and price_date - prev_date = 1
)
select
    d.day_of_week,
    d.day_name,
    p.platform_name,
    count(*)                                                                       as day_pairs,
    count(*) filter (where pr.price_idr <> pr.prev_price)                          as price_changes,
    round(100.0 * count(*) filter (where pr.price_idr <> pr.prev_price) / count(*), 1) as price_change_rate_pct,
    count(*) filter (where pr.price_idr < pr.prev_price)                           as price_drops,
    count(*) filter (where pr.price_idr > pr.prev_price)                           as price_rises
from pairs pr
join gold.dim_date d     on d.date = pr.price_date
join gold.dim_platform p on p.platform_key = pr.platform_key
group by 1, 2, 3
order by 1, 3;

{#- Ringkasan satu baris untuk kartu angka di dashboard. -#}
with fact as (
    select max(last_crawled_at) as latest_crawl_at, count(*) as fact_rows,
           count(distinct product_key) as products, count(distinct platform_key) as platforms
    from {{ ref('fct_product_price_daily') }}
),
rec as (
    select count(*) as recommendation_rows, max(run_ts) as last_recommendation_run_ts,
           (array_agg(model_version order by run_ts desc))[1] as last_model_version
    from {{ ref('fct_price_recommendation') }}
)
select
    f.latest_crawl_at,
    round((extract(epoch from (now() - f.latest_crawl_at)) / 3600)::numeric, 1) as hours_since_latest_crawl,
    case
        when now() - f.latest_crawl_at <= interval '36 hours' then 'FRESH'
        when now() - f.latest_crawl_at <= interval '72 hours' then 'WARN'
        else 'STALE'
    end as freshness_status,
    f.fact_rows, f.products, f.platforms,
    r.recommendation_rows, r.last_recommendation_run_ts, r.last_model_version
from fact f cross join rec r

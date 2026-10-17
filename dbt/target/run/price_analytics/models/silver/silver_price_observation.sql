
  create view "price_analytics"."silver"."silver_price_observation__dbt_tmp"
    
    
  as (
    with ranked as (
    select
        s.*,
        row_number() over (
            partition by platform, source_url, crawl_date
            order by crawled_at desc, raw_id desc
        ) as rn
    from "price_analytics"."silver"."stg_crawl_product_price" s
),

latest as (
    select * from ranked where rn = 1
),

branded as (
    select
        l.*,
        (select b.brand from "price_analytics"."silver"."brands" b
          where ' ' || l.name_clean || ' ' like '% ' || lower(b.brand) || ' %'
          order by length(b.brand) desc limit 1) as brand,
        c.category as category_from_breadcrumb
    from latest l
    left join "price_analytics"."silver"."category_map" c
           on c.platform = l.platform and c.breadcrumb = l.breadcrumb
),

checked as (
    select
        *,
        case
            when price_idr is null                                         then 'price_missing'
            when price_idr <= 0                                            then 'price_not_positive'
            when discount_pct_raw is not null
                 and (discount_pct_raw < 0 or discount_pct_raw > 100)      then 'discount_out_of_range'
            when original_price_idr is not null
                 and price_idr > original_price_idr                        then 'price_gt_original'
        end as dq_issue
    from branded
)

select
    md5(platform || '|' || source_url)                         as listing_key,
    md5(match_key)                                             as product_key,
    platform,
    source_url,
    crawl_date,
    crawled_at,
    product_name,
    brand,
    category_from_breadcrumb,
    pack_qty_base,
    pack_unit_base,
    match_key,
    price_idr,
    coalesce(original_price_idr, price_idr)                    as original_price_idr,
    case when price_idr > 0 and coalesce(original_price_idr, price_idr) >= price_idr
         then round((1 - price_idr / coalesce(original_price_idr, price_idr)) * 100, 1)
         else 0 end                                            as discount_pct,
    dq_issue,
    (dq_issue is null)                                         as is_valid,
    data_source,
    raw_id
from checked
  );
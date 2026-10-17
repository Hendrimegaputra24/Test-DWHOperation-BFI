{#- Dimensi riwayat (SCD Tipe 2): satu baris per listing per VERSI atributnya.
    Atribut yang dilacak: nama listing di platform dan produk kanonik yang cocok.
    Rentang berlaku diambil dari tanggal crawl, bukan dari waktu dbt dijalankan, sehingga
    riwayat tetap benar walau seluruh data dimuat sekaligus (backfill). -#}

with obs as (
    select listing_key, platform, source_url, crawl_date, product_name, product_key
    from {{ ref('silver_price_observation') }}
),

flagged as (
    select
        *,
        case when lag(product_name) over w is distinct from product_name
               or lag(product_key)  over w is distinct from product_key
             then 1 else 0 end as is_change
    from obs
    window w as (partition by listing_key order by crawl_date)
),

grouped as (
    select
        *,
        sum(is_change) over (partition by listing_key order by crawl_date
                             rows between unbounded preceding and current row) as version_no
    from flagged
),

versions as (
    select
        listing_key, platform, source_url, product_name, product_key, version_no,
        min(crawl_date) as valid_from,
        max(crawl_date) as last_seen_date
    from grouped
    group by listing_key, platform, source_url, product_name, product_key, version_no
)

select
    md5(listing_key || '|' || valid_from::text)                       as listing_version_key,
    listing_key,
    md5(platform)                                                     as platform_key,
    product_key,
    source_url,
    product_name                                                      as listing_name,
    version_no,
    valid_from,
    coalesce(lead(valid_from) over (partition by listing_key order by version_no) - 1,
             date '9999-12-31')                                       as valid_to,
    (lead(valid_from) over (partition by listing_key order by version_no) is null) as is_current,
    last_seen_date
from versions

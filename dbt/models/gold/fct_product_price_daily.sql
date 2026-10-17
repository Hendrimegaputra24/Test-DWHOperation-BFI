{{ config(
    materialized='incremental',
    unique_key=['date_key', 'product_key', 'platform_key'],
    incremental_strategy='delete+insert',
    on_schema_change='fail'
) }}

{#- Strategi incremental: setiap run hanya memproses crawl_date dalam 3 hari terakhir
    sebelum tanggal terbaru yang sudah ada di tabel ini (lookback untuk koreksi/crawl terlambat).
    Baris lama di rentang itu diganti (delete+insert) berdasarkan unique_key, sehingga aman
    dijalankan ulang tanpa duplikat. Hanya observasi valid yang masuk ke gold. -#}

select
    to_char(o.crawl_date, 'YYYYMMDD')::int                 as date_key,
    o.product_key,
    md5(o.platform)                                        as platform_key,
    o.listing_key,
    o.crawl_date                                           as price_date,
    o.price_idr,
    o.original_price_idr,
    o.original_price_idr - o.price_idr                     as discount_amount_idr,
    o.discount_pct,
    (o.discount_pct > 0)                                   as is_discounted,
    o.data_source,
    o.crawled_at                                           as last_crawled_at
from {{ ref('silver_price_observation') }} o
where o.is_valid
{% if is_incremental() %}
  and o.crawl_date >= (select coalesce(max(price_date), date '1900-01-01') - 3 from {{ this }})
{% endif %}

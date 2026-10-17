{{ config(
    materialized='incremental',
    unique_key='recommendation_key',
    on_schema_change='append_new_columns'
) }}

{#- Tabel ini hanya DIBUAT oleh dbt (struktur kosong). Baris diisi oleh model batch rekomendasi
    (Part 5). Karena incremental, dbt run berikutnya tidak menghapus rekomendasi yang sudah ada. -#}

select
    cast(null as text)             as recommendation_key,
    cast(null as integer)          as date_key,
    cast(null as text)             as product_key,
    cast(null as numeric)          as competitor_median_price_idr,
    cast(null as numeric)          as competitor_min_price_idr,
    cast(null as integer)          as competitor_count,
    cast(null as numeric)          as price_floor_idr,
    cast(null as numeric)          as recommended_price_idr,
    cast(null as text)             as rule_applied,
    cast(null as text)             as model_version,
    cast(null as text)             as run_id,
    cast(null as timestamptz)      as run_ts
where false

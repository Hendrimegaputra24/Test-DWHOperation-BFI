{% snapshot snap_platform_listing %}

{#- dbt snapshot (SCD Tipe 2) atas atribut TERBARU tiap listing. Strategi 'check': versi baru dibuat bila
    product_name atau product_key berubah. dbt_valid_from/dbt_valid_to diisi dbt (waktu snapshot dijalankan).

    Variabel snapshot_as_of_date (bawaan 9999-12-31 = keadaan terbaru) hanya untuk mendemonstrasikan riwayat:
      dbt snapshot --vars '{snapshot_as_of_date: 2026-10-01}'   lalu   dbt snapshot

    Catatan: pada pemuatan historis sekaligus hanya terbentuk satu versi; riwayat bertambah seiring snapshot
    dijalankan setelah tiap crawl. Riwayat berbasis TANGGAL CRAWL ada di gold.dim_platform_listing. -#}

{{
    config(
        target_schema='gold',
        unique_key='listing_key',
        strategy='check',
        check_cols=['product_name', 'product_key']
    )
}}

select distinct on (listing_key)
    listing_key,
    platform,
    source_url,
    product_name,
    product_key,
    brand,
    crawl_date as last_seen_date
from {{ ref('silver_price_observation') }}
where crawl_date <= '{{ var("snapshot_as_of_date", "9999-12-31") }}'::date
order by listing_key, crawl_date desc

{% endsnapshot %}

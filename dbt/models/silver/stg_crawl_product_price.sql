{#- Silver tahap 1: ubah teks mentah menjadi tipe yang benar dan siapkan kunci pencocokan produk. -#}
{%- set size_re = "(\d+(?:[.,]\d+)?)\s*(ml|kg|g|l|pcs)(?![a-z])" -%}

with src as (
    select * from {{ source('raw', 'crawl_product_price') }}
),

parsed as (
    select
        raw_id,
        platform,
        source_url,
        crawled_at,
        crawl_date,
        crawler_version,
        data_source,
        product_name,
        breadcrumb,
        -- "Rp 14.500" / "Rp14.500" -> 14500
        nullif(regexp_replace(price_text, '[^0-9]', '', 'g'), '')::numeric          as price_idr,
        nullif(regexp_replace(original_price_text, '[^0-9]', '', 'g'), '')::numeric as original_price_idr,
        -- "9%" -> 9 ; "-10%" -> -10 (nilai di luar 0..100 dibiarkan agar bisa ditandai)
        nullif(substring(discount_text from '-?[0-9]+'), '')::numeric               as discount_pct_raw,
        lower(product_name)                                                         as name_lower,
        regexp_match(lower(product_name), '{{ size_re }}')                           as size_m
    from src
),

sized as (
    select
        *,
        replace(size_m[1], ',', '.')::numeric as size_qty,
        size_m[2]                             as size_unit
    from parsed
),

normalized as (
    select
        *,
        -- satuan dasar: ml (dari ml, L), g (dari g, kg), pcs
        round(case size_unit when 'l' then size_qty * 1000
                             when 'kg' then size_qty * 1000
                             else size_qty end)::int as pack_qty_base,
        case size_unit when 'l' then 'ml' when 'ml' then 'ml'
                       when 'kg' then 'g' when 'g' then 'g'
                       when 'pcs' then 'pcs' end      as pack_unit_base,
        -- nama tanpa ukuran, tanpa tanda baca
        trim(regexp_replace(regexp_replace(name_lower, '{{ size_re }}', ' '), '[^a-z0-9]+', ' ', 'g')) as name_clean
    from sized
),

keyed as (
    select
        n.*,
        -- kumpulan kata unik (tanpa kata promosi), diurutkan, sehingga urutan kata tidak berpengaruh
        (select string_agg(distinct t, ' ' order by t)
           from unnest(string_to_array(n.name_clean, ' ')) as t
          where t <> ''
            and t not in ('official', 'store', 'isi', 'lebih', 'promo', 'pack', 'unilever')) as name_key
    from normalized n
)

select
    raw_id, platform, source_url, crawled_at, crawl_date, crawler_version, data_source,
    product_name, breadcrumb, price_idr, original_price_idr, discount_pct_raw,
    pack_qty_base, pack_unit_base, name_clean, name_key,
    name_key || '|' || coalesce(pack_qty_base::text, 'na') || coalesce(pack_unit_base, 'na') as match_key
from keyed

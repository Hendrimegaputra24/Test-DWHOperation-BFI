{#- Riwayat harga harian per produk dan platform (untuk grafik garis; filter per produk). -#}
select
    f.price_date,
    m.product_name,
    m.brand,
    m.category,
    p.platform_name,
    f.price_idr,
    f.original_price_idr,
    f.discount_pct
from {{ ref('fct_product_price_daily') }} f
join {{ ref('dim_product_master') }} m on m.product_key = f.product_key
join {{ ref('dim_platform') }} p on p.platform_key = f.platform_key

-- Tes kustom 2: persentase diskon harus berada di 0 sampai 100.
select * from {{ ref('fct_product_price_daily') }} where discount_pct < 0 or discount_pct > 100

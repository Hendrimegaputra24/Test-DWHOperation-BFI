-- Tes kustom 1: harga harus lebih dari 0.
select * from {{ ref('fct_product_price_daily') }} where price_idr <= 0

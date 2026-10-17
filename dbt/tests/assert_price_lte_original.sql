-- Tes kustom 3: harga jual tidak boleh melebihi harga asli.
select * from {{ ref('fct_product_price_daily') }} where price_idr > original_price_idr

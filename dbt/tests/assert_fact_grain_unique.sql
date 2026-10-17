-- Tes kustom 4: grain fakta = satu baris per tanggal, produk, dan platform.
select date_key, product_key, platform_key, count(*) as n
from {{ ref('fct_product_price_daily') }}
group by 1, 2, 3
having count(*) > 1

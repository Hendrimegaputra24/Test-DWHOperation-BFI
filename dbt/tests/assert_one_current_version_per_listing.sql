-- Setiap listing harus punya tepat satu versi yang berlaku saat ini.
select listing_key, count(*) filter (where is_current) as n_current
from {{ ref('dim_platform_listing') }}
group by 1
having count(*) filter (where is_current) <> 1

-- Setiap listing harus punya tepat satu versi snapshot yang berlaku saat ini (dbt_valid_to kosong).
select listing_key, count(*) as n_current
from {{ ref('snap_platform_listing') }}
where dbt_valid_to is null
group by 1
having count(*) <> 1

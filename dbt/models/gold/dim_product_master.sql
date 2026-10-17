{#- Dimensi produk kanonik (satu baris per produk, lintas platform). -#}
select
    product_key,
    case when canonical_name = upper(canonical_name)
         then initcap(lower(canonical_name)) else canonical_name end as product_name,
    brand,
    category,
    pack_qty_base,
    pack_unit_base,
    pack_size,
    n_platforms,
    first_seen_date
from {{ ref('silver_product_master') }}

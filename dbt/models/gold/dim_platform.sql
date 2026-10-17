{#- Dimensi platform. Sumber: seed platforms (data referensi kecil dan jarang berubah). -#}
select
    md5(platform_name) as platform_key,
    platform_name,
    platform_code,
    platform_type,
    base_url
from {{ ref('platforms') }}

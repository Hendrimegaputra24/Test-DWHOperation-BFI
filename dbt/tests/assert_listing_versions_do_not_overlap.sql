-- Rentang berlaku versi-versi dari listing yang sama tidak boleh tumpang tindih.
select a.listing_key, a.valid_from, b.valid_from as next_valid_from
from {{ ref('dim_platform_listing') }} a
join {{ ref('dim_platform_listing') }} b
  on a.listing_key = b.listing_key
 and a.version_no + 1 = b.version_no
where a.valid_to >= b.valid_from

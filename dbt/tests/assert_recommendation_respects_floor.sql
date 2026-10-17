-- Rekomendasi harus > 0 dan tidak boleh di bawah batas bawah margin.
select * from {{ ref('fct_price_recommendation') }}
where recommended_price_idr <= 0 or recommended_price_idr < price_floor_idr

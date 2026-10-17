
    
    

with all_values as (

    select
        category as value_field,
        count(*) as n_records

    from "price_analytics"."silver"."silver_product_master"
    group by category

)

select *
from all_values
where value_field not in (
    'Bumbu & Masakan','Minuman','Perawatan Rambut','Sabun Mandi','Perawatan Mulut','Deterjen & Pembersih'
)



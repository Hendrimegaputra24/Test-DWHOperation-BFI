
    
    

with all_values as (

    select
        platform as value_field,
        count(*) as n_records

    from "price_analytics"."raw"."crawl_product_price"
    group by platform

)

select *
from all_values
where value_field not in (
    'Klik Indomaret','Blibli','Tokopedia'
)



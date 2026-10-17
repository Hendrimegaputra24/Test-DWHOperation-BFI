
    
    

with all_values as (

    select
        n_platforms as value_field,
        count(*) as n_records

    from "price_analytics"."silver"."silver_product_master"
    group by n_platforms

)

select *
from all_values
where value_field not in (
    2,3
)



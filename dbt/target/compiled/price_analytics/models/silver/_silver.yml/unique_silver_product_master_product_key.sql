
    
    

select
    product_key as unique_field,
    count(*) as n_records

from "price_analytics"."silver"."silver_product_master"
where product_key is not null
group by product_key
having count(*) > 1



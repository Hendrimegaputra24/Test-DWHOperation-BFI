
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

with all_values as (

    select
        data_source as value_field,
        count(*) as n_records

    from "price_analytics"."raw"."crawl_product_price"
    group by data_source

)

select *
from all_values
where value_field not in (
    'live','synthetic'
)



  
  
      
    ) dbt_internal_test

    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

with all_values as (

    select
        pack_unit_base as value_field,
        count(*) as n_records

    from "price_analytics"."silver"."stg_crawl_product_price"
    group by pack_unit_base

)

select *
from all_values
where value_field not in (
    'ml','g','pcs'
)



  
  
      
    ) dbt_internal_test
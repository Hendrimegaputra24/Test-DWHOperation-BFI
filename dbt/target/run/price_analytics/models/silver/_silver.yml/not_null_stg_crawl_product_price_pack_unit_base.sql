
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select pack_unit_base
from "price_analytics"."silver"."stg_crawl_product_price"
where pack_unit_base is null



  
  
      
    ) dbt_internal_test

    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select product_key
from "price_analytics"."silver"."silver_product_master"
where product_key is null



  
  
      
    ) dbt_internal_test

    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select category
from "price_analytics"."silver"."silver_product_master"
where category is null



  
  
      
    ) dbt_internal_test
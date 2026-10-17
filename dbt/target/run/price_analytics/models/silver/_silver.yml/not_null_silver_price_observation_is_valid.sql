
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select is_valid
from "price_analytics"."silver"."silver_price_observation"
where is_valid is null



  
  
      
    ) dbt_internal_test
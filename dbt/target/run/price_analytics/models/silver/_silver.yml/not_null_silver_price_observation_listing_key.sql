
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select listing_key
from "price_analytics"."silver"."silver_price_observation"
where listing_key is null



  
  
      
    ) dbt_internal_test

    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select brand
from "price_analytics"."silver"."silver_product_master"
where brand is null



  
  
      
    ) dbt_internal_test
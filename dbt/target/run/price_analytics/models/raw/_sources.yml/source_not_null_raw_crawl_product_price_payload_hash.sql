
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select payload_hash
from "price_analytics"."raw"."crawl_product_price"
where payload_hash is null



  
  
      
    ) dbt_internal_test
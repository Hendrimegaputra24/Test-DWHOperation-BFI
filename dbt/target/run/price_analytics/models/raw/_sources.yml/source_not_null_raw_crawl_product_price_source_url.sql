
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select source_url
from "price_analytics"."raw"."crawl_product_price"
where source_url is null



  
  
      
    ) dbt_internal_test
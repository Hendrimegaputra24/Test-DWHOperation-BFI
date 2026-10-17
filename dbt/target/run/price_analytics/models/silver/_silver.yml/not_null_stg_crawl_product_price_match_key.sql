
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    



select match_key
from "price_analytics"."silver"."stg_crawl_product_price"
where match_key is null



  
  
      
    ) dbt_internal_test
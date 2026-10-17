
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

with all_values as (

    select
        platform as value_field,
        count(*) as n_records

    from "price_analytics"."silver"."silver_price_observation"
    group by platform

)

select *
from all_values
where value_field not in (
    'Klik Indomaret','Blibli','Tokopedia'
)



  
  
      
    ) dbt_internal_test
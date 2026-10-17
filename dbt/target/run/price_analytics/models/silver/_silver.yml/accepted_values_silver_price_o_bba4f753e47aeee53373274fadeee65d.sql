
    
    select
      count(*) as failures,
      count(*) != 0 as should_warn,
      count(*) != 0 as should_error
    from (
      
    
  
    
    

with all_values as (

    select
        dq_issue as value_field,
        count(*) as n_records

    from "price_analytics"."silver"."silver_price_observation"
    group by dq_issue

)

select *
from all_values
where value_field not in (
    'price_missing','price_not_positive','discount_out_of_range','price_gt_original'
)



  
  
      
    ) dbt_internal_test
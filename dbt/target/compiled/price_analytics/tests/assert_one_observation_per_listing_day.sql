-- Gagal bila ada lebih dari satu observasi untuk listing yang sama di hari yang sama.
select listing_key, crawl_date, count(*) as n
from "price_analytics"."silver"."silver_price_observation"
group by 1, 2
having count(*) > 1
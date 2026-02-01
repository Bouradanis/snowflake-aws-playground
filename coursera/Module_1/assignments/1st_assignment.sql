show warehouses;

use warehouse efouli;

SELECT CURRENT_ROLE();

SELECT CURRENT_WAREHOUSE();

SELECT CURRENT_DATABASE();

SELECT CURRENT_SCHEMA(); 

USE DATABASE tasty_bytes_sample_data;

use schema raw_pos;

select * from tasty_bytes_sample_data.raw_pos.menu;

SELECT CURRENT_DATABASE();

SELECT CURRENT_SCHEMA();

select * from menu a
where a.item_category  = 'Snack'
and a.item_subcategory = 'Warm Option';

select a.item_subcategory, max(a.sale_price_usd) 
from menu a
group by 1
order by 2 desc;

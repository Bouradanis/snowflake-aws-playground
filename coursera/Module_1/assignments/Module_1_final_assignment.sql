use database TASTY_BYTES;

use schema RAW_POS;

use warehouse compute_wh;

show views;

select * from TASTY_BYTES.RAW_POS.MENU
limit 5;

select m.MENU_ITEM_HEALTH_METRICS_OBJ['menu_item_health_metrics'][0]['ingredients']
from TASTY_BYTES.RAW_POS.MENU m;


create view tasty_bytes.raw_pos.menu_ingredients as
select m.MENU_ITEM_HEALTH_METRICS_OBJ['menu_item_health_metrics'][0]['ingredients'] as ingredients
from TASTY_BYTES.RAW_POS.MENU m;

select * from tasty_bytes.raw_pos.menu_ingredients
limit 5;

show views;

SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'TASTY_BYTES';

show materialized views;
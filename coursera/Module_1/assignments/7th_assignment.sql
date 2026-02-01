use database TASTY_BYTES;

use schema RAW_POS;

show warehouses;

use warehouse compute_wh;

show tables;

describe table menu;

select typeof(a.MENU_ITEM_HEALTH_METRICS_OBJ)
from tasty_bytes.raw_pos.menu a;

SELECT a.MENU_ITEM_HEALTH_METRICS_OBJ
FROM tasty_bytes.raw_pos.menu a
WHERE MENU_ITEM_NAME = 'Mango Sticky Rice';

SELECT a.MENU_ITEM_HEALTH_METRICS_OBJ['menu_item_health_metrics']
FROM tasty_bytes.raw_pos.menu a
WHERE MENU_ITEM_NAME = 'Mango Sticky Rice';

SELECT a.MENU_ITEM_HEALTH_METRICS_OBJ['menu_item_health_metrics'][0]['ingredients'][0]
FROM tasty_bytes.raw_pos.menu a
WHERE MENU_ITEM_NAME = 'Mango Sticky Rice';
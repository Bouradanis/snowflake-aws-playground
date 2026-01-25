create warehouse warehouse_one;

show warehouses;

create warehouse warehouse_two;

use warehouse warehouse_two;

show warehouses;

drop warehouse warehouse_two;

alter warehouse warehouse_one
set warehouse_size=SMALL;

show warehouses;

alter warehouse warehouse_one
set auto_suspend=120;

show warehouses;


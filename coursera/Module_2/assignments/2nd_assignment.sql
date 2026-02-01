drop database tasty_bytes_clone;

create  database tasty_bytes_clone
clone tasty_bytes;

show databases;

drop database tasty_bytes_clone;


use database tasty_bytes;

use schema raw_pos;

create table tasty_bytes.raw_pos.truck_clone
clone tasty_bytes.raw_pos.truck;




SELECT * FROM TASTY_BYTES.INFORMATION_SCHEMA.TABLE_STORAGE_METRICS
WHERE (TABLE_NAME = 'TRUCK_CLONE' OR TABLE_NAME = 'TRUCK')
AND TABLE_CATALOG = 'TASTY_BYTES';






use database tasty_bytes;

use schema raw_pos;

create resource monitor tasty_test_rm
WITH
    CREDIT_QUOTA = 15 -- 15 credits
    FREQUENCY = daily -- reset the monitor daily
    START_TIMESTAMP = immediately -- begin tracking immediately
    TRIGGERS
        ON 90 PERCENT DO NOTIFY; -- notify accountadmins at 80%

---> see all resource monitors
SHOW RESOURCE MONITORS;

create warehouse tasty_test_wh;

show warehouses;

alter warehouse tasty_test_wh
set resource_monitor=tasty_test_rm;

show resource monitors;


--this block was compiled in the snowsight since pycharm doesn t return a Results for query
alter resource monitor tasty_test_rm
set credit_quota=20;
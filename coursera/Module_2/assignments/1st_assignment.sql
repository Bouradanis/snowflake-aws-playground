-----------------------
--given code to run
-----------------------

CREATE or replace TABLE tasty_bytes.raw_pos.truck_dev
    CLONE tasty_bytes.raw_pos.truck;

SELECT * FROM tasty_bytes.raw_pos.truck_dev;

SET saved_query_id = LAST_QUERY_ID();

SET saved_timestamp = CURRENT_TIMESTAMP;

UPDATE tasty_bytes.raw_pos.truck_dev t
    SET t.year = (YEAR(CURRENT_DATE()) -1000);

----------

show variables;

select * from tasty_bytes.raw_pos.truck_dev
at(timestamp => $saved_timestamp::TIMESTAMP_LTZ);

select * from truck_dev
before(statement =>$saved_query_id);

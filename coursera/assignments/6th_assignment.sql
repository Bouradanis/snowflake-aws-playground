alter session set autocommit=false;



SELECT
    t.*,
    f.first_name AS franchisee_first_name,
    f.last_name AS franchisee_last_name
FROM tasty_bytes.raw_pos.truck t
JOIN tasty_bytes.raw_pos.franchise f
    ON t.franchise_id = f.franchise_id;

create view tasty_bytes.raw_pos.truck_franchise
as
    SELECT
    t.*,
    f.first_name AS franchisee_first_name,
    f.last_name AS franchisee_last_name
FROM tasty_bytes.raw_pos.truck t
JOIN tasty_bytes.raw_pos.franchise f
    ON t.franchise_id = f.franchise_id;

use database tasty_bytes;

use schema raw_pos;
    

select * from truck_franchise
limit 5;

select * from truck_franchise a
where  1=1
and a.franchisee_first_name='Sara'
and a.franchisee_last_name='Nicholson';

commit;

describe view truck_franchise;

drop view truck_franchise;

create materialized view truck_franchise_materialized --we will get error, since we are using join in a materialized view
as
SELECT
    t.*,
    f.first_name AS franchisee_first_name,
    f.last_name AS franchisee_last_name
FROM tasty_bytes.raw_pos.truck t
JOIN tasty_bytes.raw_pos.franchise f
    ON t.franchise_id = f.franchise_id;



create materialized view nissan
as
SELECT
t.*
FROM tasty_bytes.raw_pos.truck t
WHERE make = 'Nissan';

select count(*) from nissan;

drop materialized view nissan;
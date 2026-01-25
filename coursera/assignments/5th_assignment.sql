alter session set autocommit=false;
--use warehouse efouli;

--alter warehouse efouli suspend;

show warehouses;

CREATE DATABASE test_database;

CREATE SCHEMA test_database.test_schema;

USE DATABASE test_database;

USE SCHEMA test_schema;

CREATE TABLE TEST_TABLE (
	TEST_NUMBER NUMBER,
	TEST_VARCHAR VARCHAR,
	TEST_BOOLEAN BOOLEAN,
	TEST_DATE DATE,
	TEST_VARIANT VARIANT,
	TEST_GEOGRAPHY GEOGRAPHY
);

SHOW PARAMETERS LIKE 'AUTOCOMMIT';

truncate table test_table;

select * from test_table;



INSERT INTO TEST_DATABASE.TEST_SCHEMA.TEST_TABLE
  VALUES
  (28, 'ha!', True, '2024-01-01', NULL, NULL);

  commit;

  show tables;

  create table test_database.test_schema.test_table2 
  (
  test_number number
  );
truncate table test_table2;

  insert into test_database.test_schema.test_table2 (test_number)
    values (42);

    commit;

    select * from test_table2;

    show tables;

    drop table test_table;

    undrop table test_table;
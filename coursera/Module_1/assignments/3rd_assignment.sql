USE WAREHOUSE compute_wh;

CREATE DATABASE test_ingestion;

CREATE OR REPLACE FILE FORMAT test_ingestion.public.csv_ff
type = 'csv';

CREATE OR REPLACE STAGE test_ingestion.public.test_stage
url = 's3://sfquickstarts/tasty-bytes-builder-education/raw_pos/truck'
file_format = test_ingestion.public.csv_ff;

ls @test_ingestion.public.test_stage;

-- truck table build
CREATE OR REPLACE TABLE test_ingestion.public.truck
(
    truck_id NUMBER(38,0),
    menu_type_id NUMBER(38,0),
    primary_city VARCHAR(16777216),
    region VARCHAR(16777216),
    iso_region VARCHAR(16777216),
    country VARCHAR(16777216),
    iso_country_code VARCHAR(16777216),
    franchise_flag NUMBER(38,0),
    year NUMBER(38,0),
    make VARCHAR(16777216),
    model VARCHAR(16777216),
    ev_flag NUMBER(38,0),
    franchise_id NUMBER(38,0),
    truck_opening_date DATE
);

-----------------------------------------------------------------------------------------------------------------------------------------
--Clarifications:
--Since in this stage the url was 's3://sfquickstarts/tasty-bytes-builder-education/raw_pos/truck' which included the path /raw_pos/truck'
--we only need to use from @test_ingestion.public.test_stage in the COPY INTO statement

-----------------------------------------------------------------------------------------------------------------------------------------

copy into test_ingestion.public.truck
from @test_ingestion.public.test_stage;

select * from test_ingestion.public.truck;


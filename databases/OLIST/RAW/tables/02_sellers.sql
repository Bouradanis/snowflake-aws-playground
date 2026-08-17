-- Table: OLIST.RAW.SELLERS
-- Source: s3://snowflake-playground-bucket/olist/sellers/olist_sellers_dataset.csv
-- Purpose: 1:1 raw load of the Olist sellers file. Requested by data scientist,
--          Jira SNOW-3.
-- Run by: data-engineer agent, role ACCOUNTADMIN, warehouse COMPUTE_WH
--
-- TRANSIENT: fully reproducible from the S3 source, skip Fail-safe.

USE ROLE ACCOUNTADMIN;
USE DATABASE OLIST;
USE SCHEMA OLIST.RAW;

CREATE TRANSIENT TABLE IF NOT EXISTS OLIST.RAW.SELLERS (
    seller_id               VARCHAR      NOT NULL,
    seller_zip_code_prefix  VARCHAR(5),
    seller_city             VARCHAR,
    seller_state             VARCHAR(2)
)
COMMENT = 'Raw 1:1 load of olist_sellers_dataset.csv.';

COMMENT ON COLUMN OLIST.RAW.SELLERS.seller_zip_code_prefix IS 'First 5 digits of Brazilian CEP postal code, stored as VARCHAR to preserve leading zeros.';

COPY INTO OLIST.RAW.SELLERS
  FROM @OLIST.RAW.OLIST_STAGE/sellers/
  FILE_FORMAT = (FORMAT_NAME = OLIST.RAW.CSV_FORMAT)
  ON_ERROR = 'ABORT_STATEMENT';
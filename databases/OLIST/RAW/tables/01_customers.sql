-- Table: OLIST.RAW.CUSTOMERS
-- Source: s3://snowflake-playground-bucket/olist/customers/olist_customers_dataset.csv
-- Purpose: 1:1 raw load of the Olist customers file. Requested by data scientist,
--          Jira SNOW-3.
-- Run by: data-engineer agent, role ACCOUNTADMIN, warehouse COMPUTE_WH
--
-- TRANSIENT: fully reproducible from the S3 source, skip Fail-safe to save on
-- storage cost per this project's credit budget.
--
-- Columns/types confirmed against the real header + a sample of data rows in
-- olist/olist_dataset/olist_customers_dataset.csv (not assumed).

USE ROLE ACCOUNTADMIN;
USE DATABASE OLIST;
USE SCHEMA OLIST.RAW;

CREATE TRANSIENT TABLE IF NOT EXISTS OLIST.RAW.CUSTOMERS (
    customer_id               VARCHAR      NOT NULL,
    customer_unique_id        VARCHAR      NOT NULL,
    customer_zip_code_prefix  VARCHAR(5),
    customer_city             VARCHAR,
    customer_state            VARCHAR(2)
)
COMMENT = 'Raw 1:1 load of olist_customers_dataset.csv. customer_id is the per-order customer key used on ORDERS -- customer_unique_id identifies the same real-world person across repeat orders.';

COMMENT ON COLUMN OLIST.RAW.CUSTOMERS.customer_zip_code_prefix IS 'First 5 digits of Brazilian CEP postal code, stored as VARCHAR to preserve leading zeros.';

COPY INTO OLIST.RAW.CUSTOMERS
  FROM @OLIST.RAW.OLIST_STAGE/customers/
  FILE_FORMAT = (FORMAT_NAME = OLIST.RAW.CSV_FORMAT)
  ON_ERROR = 'ABORT_STATEMENT';
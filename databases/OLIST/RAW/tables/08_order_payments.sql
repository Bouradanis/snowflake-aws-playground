-- Table: OLIST.RAW.ORDER_PAYMENTS
-- Source: s3://snowflake-playground-bucket/olist/order_payments/olist_order_payments_dataset.csv
-- Purpose: 1:1 raw load of the Olist order payments file. Requested by data
--          scientist, Jira SNOW-3.
-- Run by: data-engineer agent, role ACCOUNTADMIN, warehouse COMPUTE_WH
--
-- TRANSIENT: fully reproducible from the S3 source, skip Fail-safe.

USE ROLE ACCOUNTADMIN;
USE DATABASE OLIST;
USE SCHEMA OLIST.RAW;

CREATE TRANSIENT TABLE IF NOT EXISTS OLIST.RAW.ORDER_PAYMENTS (
    order_id               VARCHAR       NOT NULL,
    payment_sequential      NUMBER(3,0)  NOT NULL,
    payment_type            VARCHAR(20),
    payment_installments     NUMBER(3,0),
    payment_value            NUMBER(10,2)
)
COMMENT = 'Raw 1:1 load of olist_order_payments_dataset.csv -- an order can have multiple payment rows (split/combined payment methods). (order_id, payment_sequential) is the natural key.';

COMMENT ON COLUMN OLIST.RAW.ORDER_PAYMENTS.payment_sequential IS 'Sequence number of this payment within the order (an order can be paid with multiple methods).';

COPY INTO OLIST.RAW.ORDER_PAYMENTS
  FROM @OLIST.RAW.OLIST_STAGE/order_payments/
  FILE_FORMAT = (FORMAT_NAME = OLIST.RAW.CSV_FORMAT)
  ON_ERROR = 'ABORT_STATEMENT';
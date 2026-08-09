-- Table: OLIST.RAW.ORDERS
-- Source: s3://snowflake-playground-bucket/olist/orders/olist_orders_dataset.csv
-- Purpose: 1:1 raw load of the Olist orders file. Requested by data scientist,
--          Jira SNOW-3.
-- Run by: data-engineer agent, role ACCOUNTADMIN, warehouse COMPUTE_WH
--
-- TRANSIENT: fully reproducible from the S3 source, skip Fail-safe.

USE ROLE ACCOUNTADMIN;
USE DATABASE OLIST;
USE SCHEMA OLIST.RAW;

CREATE TRANSIENT TABLE IF NOT EXISTS OLIST.RAW.ORDERS (
    order_id                        VARCHAR      NOT NULL,
    customer_id                     VARCHAR      NOT NULL,
    order_status                    VARCHAR(20),
    order_purchase_timestamp        TIMESTAMP_NTZ,
    order_approved_at               TIMESTAMP_NTZ,
    order_delivered_carrier_date    TIMESTAMP_NTZ,
    order_delivered_customer_date   TIMESTAMP_NTZ,
    order_estimated_delivery_date   TIMESTAMP_NTZ
)
COMMENT = 'Raw 1:1 load of olist_orders_dataset.csv. order_id is the primary key -- customer_id joins to OLIST.RAW.CUSTOMERS (one customer_id per order, not per person -- see CUSTOMERS.customer_unique_id for the person-level key).';

COPY INTO OLIST.RAW.ORDERS
  FROM @OLIST.RAW.OLIST_STAGE/orders/
  FILE_FORMAT = (FORMAT_NAME = OLIST.RAW.CSV_FORMAT)
  ON_ERROR = 'ABORT_STATEMENT';
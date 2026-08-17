-- Table: OLIST.RAW.ORDER_ITEMS
-- Source: s3://snowflake-playground-bucket/olist/order_items/olist_order_items_dataset.csv
-- Purpose: 1:1 raw load of the Olist order items file. Requested by data scientist,
--          Jira SNOW-3.
-- Run by: data-engineer agent, role ACCOUNTADMIN, warehouse COMPUTE_WH
--
-- TRANSIENT: fully reproducible from the S3 source, skip Fail-safe.

USE ROLE ACCOUNTADMIN;
USE DATABASE OLIST;
USE SCHEMA OLIST.RAW;

CREATE TRANSIENT TABLE IF NOT EXISTS OLIST.RAW.ORDER_ITEMS (
    order_id              VARCHAR       NOT NULL,
    order_item_id         NUMBER(5,0)   NOT NULL,
    product_id            VARCHAR       NOT NULL,
    seller_id             VARCHAR       NOT NULL,
    shipping_limit_date   TIMESTAMP_NTZ,
    price                 NUMBER(10,2),
    freight_value         NUMBER(10,2)
)
COMMENT = 'Raw 1:1 load of olist_order_items_dataset.csv -- one row per line item within an order (order_id, order_item_id) is the natural key.';

COMMENT ON COLUMN OLIST.RAW.ORDER_ITEMS.order_item_id IS 'Sequential line-item number within an order, starting at 1 -- not a globally unique id.';

COPY INTO OLIST.RAW.ORDER_ITEMS
  FROM @OLIST.RAW.OLIST_STAGE/order_items/
  FILE_FORMAT = (FORMAT_NAME = OLIST.RAW.CSV_FORMAT)
  ON_ERROR = 'ABORT_STATEMENT';
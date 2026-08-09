-- Table: OLIST.RAW.PRODUCTS
-- Source: s3://snowflake-playground-bucket/olist/products/olist_products_dataset.csv
-- Purpose: 1:1 raw load of the Olist products file. Requested by data scientist,
--          Jira SNOW-3.
-- Run by: data-engineer agent, role ACCOUNTADMIN, warehouse COMPUTE_WH
--
-- TRANSIENT: fully reproducible from the S3 source, skip Fail-safe.
--
-- NOTE: product_name_lenght / product_description_lenght are misspelled
-- ("lenght" not "length") in the actual source header -- kept as-is to match the
-- real column names rather than silently renaming, flagged here so it's not
-- mistaken for a typo introduced by this DDL.

USE ROLE ACCOUNTADMIN;
USE DATABASE OLIST;
USE SCHEMA OLIST.RAW;

CREATE TRANSIENT TABLE IF NOT EXISTS OLIST.RAW.PRODUCTS (
    product_id                    VARCHAR       NOT NULL,
    product_category_name          VARCHAR,
    product_name_lenght             NUMBER(10,0),
    product_description_lenght      NUMBER(10,0),
    product_photos_qty              NUMBER(10,0),
    product_weight_g                NUMBER(10,0),
    product_length_cm               NUMBER(10,0),
    product_height_cm               NUMBER(10,0),
    product_width_cm                NUMBER(10,0)
)
COMMENT = 'Raw 1:1 load of olist_products_dataset.csv. product_category_name is the Portuguese category slug -- joins to OLIST.RAW.PRODUCT_CATEGORY_NAME_TRANSLATION for the English name.';

COMMENT ON COLUMN OLIST.RAW.PRODUCTS.product_name_lenght IS 'Character length of the product name. Misspelled in the source file ("lenght") -- kept as-is rather than renamed, to match the real column name.';
COMMENT ON COLUMN OLIST.RAW.PRODUCTS.product_description_lenght IS 'Character length of the product description. Misspelled in the source file ("lenght") -- kept as-is rather than renamed, to match the real column name.';

COPY INTO OLIST.RAW.PRODUCTS
  FROM @OLIST.RAW.OLIST_STAGE/products/
  FILE_FORMAT = (FORMAT_NAME = OLIST.RAW.CSV_FORMAT)
  ON_ERROR = 'ABORT_STATEMENT';
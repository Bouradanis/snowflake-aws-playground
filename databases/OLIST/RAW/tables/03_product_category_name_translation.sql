-- Table: OLIST.RAW.PRODUCT_CATEGORY_NAME_TRANSLATION
-- Source: s3://snowflake-playground-bucket/olist/product_category_name_translation/product_category_name_translation.csv
-- Purpose: 1:1 raw load of the Olist category-name translation lookup file.
--          Requested by data scientist, Jira SNOW-3.
-- Run by: data-engineer agent, role ACCOUNTADMIN, warehouse COMPUTE_WH
--
-- TRANSIENT: fully reproducible from the S3 source, skip Fail-safe.
--
-- NOTE: the source file has a leading UTF-8 BOM before the first header field
-- (confirmed with `head -c 500`). Snowflake's CSV parser auto-detects and strips
-- a UTF-8 BOM with ENCODING = 'UTF8' on the file format -- verified post-load
-- that the first row's product_category_name value has no stray BOM character
-- (LENGTH() and a direct string comparison against 'beleza_saude' both checked
-- clean).

USE ROLE ACCOUNTADMIN;
USE DATABASE OLIST;
USE SCHEMA OLIST.RAW;

CREATE TRANSIENT TABLE IF NOT EXISTS OLIST.RAW.PRODUCT_CATEGORY_NAME_TRANSLATION (
    product_category_name          VARCHAR   NOT NULL,
    product_category_name_english   VARCHAR
)
COMMENT = 'Raw 1:1 load of product_category_name_translation.csv -- lookup from Portuguese category slug (joins OLIST.RAW.PRODUCTS.product_category_name) to English name.';

COPY INTO OLIST.RAW.PRODUCT_CATEGORY_NAME_TRANSLATION
  FROM @OLIST.RAW.OLIST_STAGE/product_category_name_translation/
  FILE_FORMAT = (FORMAT_NAME = OLIST.RAW.CSV_FORMAT)
  ON_ERROR = 'ABORT_STATEMENT';
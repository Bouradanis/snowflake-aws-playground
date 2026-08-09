-- File format: OLIST.RAW.CSV_FORMAT
-- Purpose: shared CSV parsing spec for all 9 Olist source files.
-- Requested by: data scientist, via Jira SNOW-3
-- Run by: data-engineer agent, role ACCOUNTADMIN, warehouse COMPUTE_WH
--
-- Confirmed against the actual files in olist/olist_dataset/*.csv before writing
-- this (do not assume defaults):
--   - comma-delimited, header row present on every file (SKIP_HEADER = 1)
--   - fields are OPTIONALLY double-quoted -- some rows quote every field, others
--     leave unquoted values unquoted (e.g. bare hex ids), so
--     FIELD_OPTIONALLY_ENCLOSED_BY = '"' is required, not a plain delimiter split
--   - olist_order_reviews_dataset.csv has review_comment_title/review_comment_message
--     values that contain embedded newlines inside quoted fields (RFC4180-style) --
--     `wc -l` on that file therefore overcounts "rows" (104,719 lines vs. 99,224 true
--     CSV records, confirmed with Python's csv module). Snowflake's CSV parser handles
--     embedded newlines inside quoted fields correctly as long as
--     FIELD_OPTIONALLY_ENCLOSED_BY is set, which it is here -- but row-count
--     verification after COPY INTO must use the true record count, not `wc -l`.
--     See Confluence SN page "Gotcha: `wc -l` undercounts/overcounts CSV rows with
--     embedded newlines (Olist order_reviews)" for the full writeup.
--   - empty fields (e.g. missing review_comment_title) should load as SQL NULL,
--     not empty string -> EMPTY_FIELD_AS_NULL = TRUE
--   - product_category_name_translation.csv has an ambient UTF-8 BOM before the
--     first header field -- ENCODING = 'UTF8' (Snowflake auto-detects and strips
--     a leading UTF-8 BOM on load); verified post-load that the first column value
--     has no stray BOM character.

USE ROLE ACCOUNTADMIN;
USE DATABASE OLIST;
USE SCHEMA OLIST.RAW;

CREATE FILE FORMAT IF NOT EXISTS OLIST.RAW.CSV_FORMAT
  TYPE = 'CSV'
  FIELD_DELIMITER = ','
  SKIP_HEADER = 1
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  EMPTY_FIELD_AS_NULL = TRUE
  ENCODING = 'UTF8'
  COMPRESSION = 'AUTO'
  COMMENT = 'Shared CSV format for the 9 Olist source files -- comma-delimited, optional double-quote enclosure, header row skipped, empty fields as NULL.';
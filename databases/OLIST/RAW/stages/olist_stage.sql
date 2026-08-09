-- Stage: OLIST.RAW.OLIST_STAGE
-- Purpose: external stage over the Olist S3 bucket, backed by the storage
--          integration olist_s3_int (already created by the user in Snowsight --
--          see databases/OLIST/RAW/stages/olist_s3_int.sql, a mirrored copy of
--          olist/dataset_ingestion/Dataset_staging.sql, not re-run here).
-- Requested by: data scientist, via Jira SNOW-3
-- Run by: data-engineer agent, role ACCOUNTADMIN, warehouse COMPUTE_WH
--
-- Verified with `LIST @OLIST.RAW.OLIST_STAGE;` immediately after creation -- see
-- Jira SNOW-3 comment for the file listing returned.

USE ROLE ACCOUNTADMIN;
USE DATABASE OLIST;
USE SCHEMA OLIST.RAW;

CREATE STAGE IF NOT EXISTS OLIST.RAW.OLIST_STAGE
  STORAGE_INTEGRATION = olist_s3_int
  URL = 's3://snowflake-playground-bucket/olist/'
  FILE_FORMAT = OLIST.RAW.CSV_FORMAT
  COMMENT = 'External stage over s3://snowflake-playground-bucket/olist/ (one prefix per Olist table), backed by storage integration olist_s3_int.';

LIST @OLIST.RAW.OLIST_STAGE;
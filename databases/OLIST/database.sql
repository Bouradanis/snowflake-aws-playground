-- Database: OLIST
-- Purpose: root database for the Olist e-commerce dataset used in SNOW-1
--          (Cortex Analyst + AWS comparison against oci-ai-playground's Olist Copilot).
-- Requested by: data scientist, via Jira SNOW-3
--          ("Load Olist dataset into Snowflake via S3 external stage (OLIST schema)")
-- Run by: data-engineer agent, role ACCOUNTADMIN, warehouse COMPUTE_WH
--
-- Not marked TRANSIENT at the database level -- individual RAW-zone tables are
-- created TRANSIENT (see databases/OLIST/RAW/tables/*.sql) since they're fully
-- reproducible from the S3 source. Future schemas under this database (e.g. a
-- semantic-model / feature layer) may want normal Fail-safe/Time Travel behavior,
-- so the database itself is left as a standard (non-transient) database.

USE ROLE ACCOUNTADMIN;

CREATE DATABASE IF NOT EXISTS OLIST
  COMMENT = 'Olist Brazilian e-commerce dataset -- SNOW-1 (Cortex Analyst + AWS), loaded from S3 via storage integration olist_s3_int.';
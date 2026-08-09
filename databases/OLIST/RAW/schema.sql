-- Schema: OLIST.RAW
-- Purpose: landing zone for the 9 Olist CSVs loaded as-is from S3, one table per
--          source file, no transformation. Mirrors the raw/landing-zone naming
--          pattern already used in coursera/Module_1 (raw_pos).
-- Requested by: data scientist, via Jira SNOW-3
-- Run by: data-engineer agent, role ACCOUNTADMIN, warehouse COMPUTE_WH

USE ROLE ACCOUNTADMIN;
USE DATABASE OLIST;

CREATE SCHEMA IF NOT EXISTS OLIST.RAW
  COMMENT = 'Raw landing zone -- 1:1 load of the 9 Olist CSVs from s3://snowflake-playground-bucket/olist/, no transformation.';
-- Table: OLIST.RAW.GEOLOCATION
-- Source: s3://snowflake-playground-bucket/olist/geolocation/olist_geolocation_dataset.csv
-- Purpose: 1:1 raw load of the Olist geolocation file. Requested by data scientist,
--          Jira SNOW-3.
-- Run by: data-engineer agent, role ACCOUNTADMIN, warehouse COMPUTE_WH
--
-- TRANSIENT: fully reproducible from the S3 source, skip Fail-safe.
-- This is by far the largest file (~1M rows, many duplicate zip prefixes with
-- slightly different lat/lng samples) -- no dedup applied here, raw zone is a
-- faithful copy of the source.

USE ROLE ACCOUNTADMIN;
USE DATABASE OLIST;
USE SCHEMA OLIST.RAW;

CREATE TRANSIENT TABLE IF NOT EXISTS OLIST.RAW.GEOLOCATION (
    geolocation_zip_code_prefix  VARCHAR(5),
    geolocation_lat              FLOAT,
    geolocation_lng              FLOAT,
    geolocation_city             VARCHAR,
    geolocation_state            VARCHAR(2)
)
COMMENT = 'Raw 1:1 load of olist_geolocation_dataset.csv. Many rows per zip prefix (repeated geocode samples) -- not deduplicated in the raw zone.';

COMMENT ON COLUMN OLIST.RAW.GEOLOCATION.geolocation_zip_code_prefix IS 'First 5 digits of Brazilian CEP postal code, stored as VARCHAR to preserve leading zeros.';
COMMENT ON COLUMN OLIST.RAW.GEOLOCATION.geolocation_lat IS 'Latitude, stored as FLOAT (source values carry up to ~14 significant decimal digits).';
COMMENT ON COLUMN OLIST.RAW.GEOLOCATION.geolocation_lng IS 'Longitude, stored as FLOAT (source values carry up to ~14 significant decimal digits).';

COPY INTO OLIST.RAW.GEOLOCATION
  FROM @OLIST.RAW.OLIST_STAGE/geolocation/
  FILE_FORMAT = (FORMAT_NAME = OLIST.RAW.CSV_FORMAT)
  ON_ERROR = 'ABORT_STATEMENT';
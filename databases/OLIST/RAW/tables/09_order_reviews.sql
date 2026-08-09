-- Table: OLIST.RAW.ORDER_REVIEWS
-- Source: s3://snowflake-playground-bucket/olist/order_reviews/olist_order_reviews_dataset.csv
-- Purpose: 1:1 raw load of the Olist order reviews file. Requested by data
--          scientist, Jira SNOW-3.
-- Run by: data-engineer agent, role ACCOUNTADMIN, warehouse COMPUTE_WH
--
-- TRANSIENT: fully reproducible from the S3 source, skip Fail-safe.
--
-- GOTCHA (see Confluence SN page): review_comment_title/review_comment_message
-- contain embedded newlines inside quoted CSV fields. `wc -l` on the source file
-- reports 104,719 lines but there are only 99,224 true CSV records (confirmed
-- with Python's csv module). Snowflake's CSV parser handles this correctly
-- because FIELD_OPTIONALLY_ENCLOSED_BY = '"' is set on OLIST.RAW.CSV_FORMAT --
-- row-count verification after COPY INTO must use the true record count
-- (99,224), not `wc -l`.

USE ROLE ACCOUNTADMIN;
USE DATABASE OLIST;
USE SCHEMA OLIST.RAW;

CREATE TRANSIENT TABLE IF NOT EXISTS OLIST.RAW.ORDER_REVIEWS (
    review_id                 VARCHAR       NOT NULL,
    order_id                  VARCHAR       NOT NULL,
    review_score               NUMBER(1,0),
    review_comment_title       VARCHAR,
    review_comment_message     VARCHAR,
    review_creation_date       TIMESTAMP_NTZ,
    review_answer_timestamp    TIMESTAMP_NTZ
)
COMMENT = 'Raw 1:1 load of olist_order_reviews_dataset.csv. review_comment_title/message may contain embedded newlines inside the original quoted CSV fields -- see file format comment on OLIST.RAW.CSV_FORMAT and Confluence SN gotcha page for why `wc -l` misreports this file''s row count.';

COPY INTO OLIST.RAW.ORDER_REVIEWS
  FROM @OLIST.RAW.OLIST_STAGE/order_reviews/
  FILE_FORMAT = (FORMAT_NAME = OLIST.RAW.CSV_FORMAT)
  ON_ERROR = 'ABORT_STATEMENT';
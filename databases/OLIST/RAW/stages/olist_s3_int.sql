-- Storage integration: olist_s3_int
-- MIRRORED COPY -- not executed by the data-engineer agent.
--
-- This statement was already run by the user directly in Snowsight, before the
-- databases/ DDL convention existed. The original, source-of-truth file is
-- olist/dataset_ingestion/Dataset_staging.sql -- left untouched per instruction.
-- This copy exists purely so that everything OLIST-related is discoverable under
-- databases/OLIST/ per the repo's DDL convention. If the two files ever diverge,
-- olist/dataset_ingestion/Dataset_staging.sql is the one that actually ran.
--
-- STORAGE_AWS_ROLE_ARN points at IAM role snowflake_olist_role
-- (arn:aws:iam::729297430341:role/snowflake_olist_role), trust-policy-scoped to
-- Snowflake's IAM user for this account (arn:aws:iam::465573888563:user/zprw1000-s)
-- plus external ID, both obtained from `DESC STORAGE INTEGRATION olist_s3_int;`
-- after the first (placeholder) pass. Confirmed live and connected -- do not
-- recreate; referenced by name from databases/OLIST/RAW/stages/olist_stage.sql.

USE ROLE ACCOUNTADMIN;

CREATE STORAGE INTEGRATION olist_s3_int
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  ENABLED = TRUE
  STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::729297430341:role/snowflake_olist_role'
  STORAGE_ALLOWED_LOCATIONS = ('s3://snowflake-playground-bucket/olist/');

DESC STORAGE INTEGRATION olist_s3_int;
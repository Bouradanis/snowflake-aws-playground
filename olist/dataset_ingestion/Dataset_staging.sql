use role accountadmin;

CREATE STORAGE INTEGRATION olist_s3_int
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  ENABLED = TRUE
  STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::729297430341:role/snowflake_olist_role'
  STORAGE_ALLOWED_LOCATIONS = ('s3://snowflake-playground-bucket/olist/');

DESC STORAGE INTEGRATION olist_s3_int;
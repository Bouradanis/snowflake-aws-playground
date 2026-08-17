-- Schema: OLIST.SNOWSTRIDER_SPIKE
-- Purpose: throwaway schema for the SNOW-4 Container Runtime feasibility spike --
--          "can this trial account run Streamlit-in-Snowflake Container Runtime
--          (compute pool + external access integration to PyPI), sufficient to
--          import real langgraph/sqlglot (confirmed absent from the Anaconda
--          channel used by SiS Warehouse Runtime)?"
-- Requested by: data scientist, via Jira SNOW-4 (subtask of epic SNOW-1)
-- Run by: data-engineer agent, role ACCOUNTADMIN, warehouse COMPUTE_WH
--
-- ALL OBJECTS IN THIS SCHEMA (schema, network rule, external access integration,
-- stage, streamlit app, compute pool) WERE DROPPED at the end of the spike --
-- this file (and the sibling files in stages/) records what was actually run,
-- not what is currently live. See Confluence SN "SNOW-4: Container Runtime SiS
-- feasibility spike" for the outcome and DESCRIBE-STREAMLIT/service-log evidence.

USE ROLE ACCOUNTADMIN;
USE DATABASE OLIST;

CREATE SCHEMA IF NOT EXISTS OLIST.SNOWSTRIDER_SPIKE
  COMMENT = 'Throwaway schema for the SNOW-4 Container Runtime SiS feasibility spike. Dropped after the spike concluded.';

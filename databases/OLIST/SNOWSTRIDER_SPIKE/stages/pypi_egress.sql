-- Network rule + external access integration: SNOWSTRIDER_SPIKE_PYPI_RULE / _EAI
-- Purpose: allow the SNOW-4 spike's Container Runtime Streamlit app to reach PyPI
--          (pypi.org + files.pythonhosted.org) to pip-install langgraph/sqlglot at
--          service startup, per Snowflake's documented pattern for Container
--          Runtime SiS dependency installation.
-- Requested by: data scientist, via Jira SNOW-4
-- Run by: data-engineer agent, role ACCOUNTADMIN, warehouse COMPUTE_WH
--
-- DROPPED at the end of the spike -- see databases/OLIST/SNOWSTRIDER_SPIKE/schema.sql
-- header for why this schema/its objects no longer exist.

USE ROLE ACCOUNTADMIN;
USE DATABASE OLIST;
USE SCHEMA OLIST.SNOWSTRIDER_SPIKE;

CREATE OR REPLACE NETWORK RULE snowstrider_spike_pypi_rule
  MODE = EGRESS
  TYPE = HOST_PORT
  VALUE_LIST = ('pypi.org', 'files.pythonhosted.org')
  COMMENT = 'Egress allowlist for pip installs from PyPI -- SNOW-4 Container Runtime spike.';

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION snowstrider_spike_eai
  ALLOWED_NETWORK_RULES = (snowstrider_spike_pypi_rule)
  ENABLED = TRUE
  COMMENT = 'External access integration granting the SNOW-4 spike Streamlit app egress to PyPI for langgraph/sqlglot installation.';

-- Stage: OLIST.SNOWSTRIDER_SPIKE.SNOWSTRIDER_SPIKE_STAGE
-- Purpose: holds app.py + environment.yml for the SNOW-4 Container Runtime spike's
--          minimal Streamlit app (imports langgraph + sqlglot, builds/runs a
--          trivial 2-node StateGraph).
-- Requested by: data scientist, via Jira SNOW-4
-- Run by: data-engineer agent, role ACCOUNTADMIN, warehouse COMPUTE_WH
--
-- Files were PUT onto this stage from a Snowpark session (session.file.put), not
-- tracked here since PUT is a client-side file transfer, not DDL. The source
-- files are preserved in this repo's data-engineer session scratchpad, not the
-- repo itself (they were throwaway spike code, not the real Snowstrider app).
--
-- DROPPED at the end of the spike -- see schema.sql header.

USE ROLE ACCOUNTADMIN;
USE DATABASE OLIST;
USE SCHEMA OLIST.SNOWSTRIDER_SPIKE;

CREATE STAGE IF NOT EXISTS snowstrider_spike_stage
  DIRECTORY = (ENABLE = TRUE)
  COMMENT = 'Holds app.py + environment.yml for the SNOW-4 Container Runtime feasibility spike.';

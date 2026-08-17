# Snowstrider

A standalone Streamlit app that answers natural-language questions over the `OLIST.RAW`
schema in Snowflake via a LangGraph state machine (generate SQL -> validate -> execute ->
retry-on-error -> self-check plausibility -> chart spec -> render). It's the hand-rolled
comparison arm of Jira `SNOW-1`: Snowflake Cortex Analyst is blocked on this trial account,
so this is the "build the text-to-SQL loop yourself" counterpart, directly comparable to
`oci-ai-playground`'s Olist Copilot chat page. See `CLAUDE.md` at the repo root for the
fuller history, including why this app is standalone rather than Streamlit-in-Snowflake.

## Running locally

```bash
pip install -r requirements.txt
```

Set `ANTHROPIC_API_KEY` in a repo-root `.env` file (this repo's existing convention --
gitignored, never committed):

```
ANTHROPIC_API_KEY=sk-ant-...
```

Then, from the repo root:

```bash
streamlit run snowstrider/app.py
```

**Snowflake credentials are entered in-app at login, not via `.env`.** This differs from
the rest of this repo's scripts, which read `SNOWFLAKE_ACCOUNT` / `SNOWFLAKE_USER` /
`SNOWFLAKE_PASSWORD` from `.env`. Snowstrider is a multi-user app in principle (Streamlit
Community Cloud has no per-deployment secret store for *your* Snowflake login, only the
app owner's `st.secrets`), so each user logs in with their own Snowflake account identifier,
username, and password on the app's login screen. That login is the app's entire auth
mechanism -- there is no separate user database, session token, or password of its own.
Nothing entered there is logged, printed, or persisted by the app.

## Deploying to Streamlit Community Cloud

- `ANTHROPIC_API_KEY` goes in the deployed app's **secrets** (Community Cloud dashboard ->
  app settings -> Secrets, as TOML: `ANTHROPIC_API_KEY = "sk-ant-..."`), never committed to
  the repo. `snowflake_conn.get_anthropic_client()` already checks `st.secrets` first and
  falls back to `.env` for local runs, so no code change is needed to switch between the two.
- Snowflake credentials still come from the in-app login form -- nothing to configure for
  that in Community Cloud secrets.
- **Open item, not yet confirmed:** whether this GitHub repo is public or private, and what
  that implies for Community Cloud deployment (public repos deploy to a publicly *loadable*
  app URL; private repos need a paid/connected-org tier or an invite-only setup -- don't take
  this as settled, check Community Cloud's current docs/plan before deploying). Either way,
  the app-level Snowflake login is the real access gate: even if the app's URL itself is
  publicly reachable, nobody gets past the login screen without a real Snowflake account in
  this trial's account, so there's no separate "make it private" step needed for the data
  itself.

## Architecture note

This app was originally scoped as Streamlit-in-Snowflake (Container Runtime, for real
`langgraph`/`sqlglot` support). That path is blocked on this trial account -- Container
Runtime requires an External Access Integration, and trial accounts hard-block EAI creation
(confirmed via a live spike, `509009` error). See `CLAUDE.md`'s "Front end -- resolved
(SNOW-4)" note and the corresponding Confluence page (space `SN`) for the full diagnosis.
Snowstrider was pivoted to this standalone form instead: a per-session Snowpark `Session`
opened from credentials entered in the app, with full pip freedom for `langgraph`.

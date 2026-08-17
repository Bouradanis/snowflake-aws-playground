"""Streamlit page modules for Snowstrider (SNOW-7 multi-page restructure).

Named `pages_` (trailing underscore), not `pages` -- Streamlit's *legacy*
multipage-app mechanism auto-discovers a plain `pages/` directory next to the
entrypoint script and turns every `.py` file in it into a page with zero
`st.navigation` code. This app uses the newer, explicit `st.navigation`/
`st.Page` API instead (`app.py` builds the nav from the callables in this
package), and Streamlit's own docs confirm that once any session calls
`st.navigation`, a `pages/` directory is ignored app-wide anyway -- so a
same-named directory would not actually collide. The `pages_` name is kept
regardless, to avoid relying on that undocumented-in-code fallback behavior
and to make it visually obvious at a glance that these modules are wired
explicitly in `app.py`, not auto-discovered.
"""

from __future__ import annotations

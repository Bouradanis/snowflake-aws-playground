---
name: creating-project-showcase
description: Use when a mini-app or feature in this repo is finished, live-verified, and ready to be published as a promotional one-page HTML case study on the project's GitHub Pages wall (docs/).
---

# Creating a Project Showcase Page

## Overview

Each finished piece of work gets a self-contained HTML case-study page under
`docs/<project-slug>/index.html`, linked from a hub at `docs/index.html`, served
via GitHub Pages.

**This matters more here than it looks.** The Snowflake account is a 30-day trial —
whatever gets built stops being reachable when it expires, and Streamlit in Snowflake
was never publicly shareable to begin with (viewers need a Snowflake login). The
case-study page is therefore not a nice-to-have summary; it is the *only* durable,
publicly-visible artifact of this work. Capture screenshots and real numbers **while
the account is still live** — you cannot go back for them afterwards.

## Reference example

The sibling repo `oci-ai-playground` has a complete, real page at
`docs/olist-copilot/index.html`. Copy its structure rather than starting from a blank
file. It has:
- A two-column hero: headline + pitch on one side, a real screenshot on the other
- A stat strip in monospace tabular numbers (real figures, not placeholders)
- A feature list in the app's actual nav order (not a generic icon-card grid)
- An architecture pipeline built from flex boxes + arrows (no Mermaid/CDN — see below)
- A filmstrip of real screenshots with captions
- A tech-stack tag list and footer linking back to `docs/index.html` and the GitHub repo

## Workflow

1. Pull real assets first: screenshots from `screenshots/` (or wherever the feature's
   agent saved them), real stats from the app itself — never placeholder numbers or
   lorem text. Do this before the trial lapses.
2. Adapt every section's content and the `assets/` images for the new project. Keep the
   token-based light/dark CSS pattern (`:root` custom properties, overridden under
   `prefers-color-scheme` and `data-theme`) — don't hardcode colors inline.
3. Everything stays self-contained: inline CSS, system font stacks, no external
   font/script CDN. GitHub Pages has no CSP that would block a CDN, but keeping it
   dependency-free means the same file also previews cleanly as a Claude Artifact
   before it's committed.
4. Add a card for the new project to `docs/index.html`'s grid.
5. Preview via the Artifact tool before committing (point it at the real file path in
   `docs/`, not a copy) — catch layout/content issues while it's cheap to fix.
6. **Scrub before publishing.** This repo is public and the page is promotional, so it's
   exactly where a Snowflake account identifier, a warehouse name, or a region slug slips
   out in a screenshot. Check the images, not just the HTML.
7. GitHub Pages needs enabling once per repo (Settings → Pages → source = `main` branch,
   `/docs` folder) — a repo-settings change, so confirm with the user rather than
   assuming it's already on.
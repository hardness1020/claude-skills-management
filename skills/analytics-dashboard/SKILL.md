---
name: analytics-dashboard
description: Launch the skills analytics dashboard to view usage metrics, scores, and trends
metadata:
  triggers:
    - analytics dashboard
    - skill analytics
    - usage dashboard
    - open dashboard
---

# analytics-dashboard

Launch the skills analytics dashboard — a local web UI for viewing skill usage frequency, adoption curves, usefulness scores, trends, and structure coverage.

## Usage

When the user asks to open or view the analytics dashboard, start the Django development server:

```bash
cd "${CLAUDE_PLUGIN_ROOT}" && uv run python -m django runserver 8787 --settings=dashboard.analytics_project.settings
```

Then tell the user:

> The dashboard is running at **http://localhost:8787**
>
> Open it in your browser to view:
> - **Usefulness** — composite scores with usage rate, decay, and depth breakdown
> - **Usage** — frequency rankings and time-series trends
> - **Inventory** — all registered skills with status and metadata
>
> To stop the server, press **Ctrl+C** in the terminal or kill the process.

## Notes

- The dashboard reads from the shared SQLite database at `${CLAUDE_PLUGIN_DATA}/skills_analytics.db`
- Data is collected automatically by the plugin's hooks (PreToolUse and UserPromptSubmit)
- The server runs on localhost only — no external access
- Port 8787 is used by default; if it's busy, the server will report an error

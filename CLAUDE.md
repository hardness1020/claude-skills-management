# CLAUDE.md

## Plugin Release

To push changes to the marketplace, bump the version in `.claude-plugin/plugin.json` before committing. Without a version bump, `claude plugin update` will not pick up new code.

## Python

Always use `uv run python` instead of `python3` or `pip` for all Python commands.

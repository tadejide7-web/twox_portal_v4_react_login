# 2X Assessment Portal

React website + FastAPI backend + SQLite, with login and roles.

    backend/   API, rules engine, login, roles, database
    web/       React website (Vite)
    tests/     engine, login and role tests (pytest)
    legacy/    earlier Streamlit interface (no longer used)

Rules: each rule is met when any one of its conditions is satisfied and its evidence is Verified.
Every met rule sets "2X Woman-Owned" and "2X Qualified". Thresholds are configurable (see `thresholds.example.json`).
See DEPLOY.md for deployment and the role table.

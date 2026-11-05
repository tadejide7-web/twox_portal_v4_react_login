# Deploying the 2X Assessment Portal

Two Render services are created from `render.yaml`:
`twox-api` (FastAPI backend, SQLite on a persistent disk) and `twox-web` (React website).

## 1. GitHub
Create an empty private repository and upload the contents of this folder (not the folder itself).
`render.yaml` must be at the top level. Turn on hidden files so `.gitignore` and `.github` are included.

## 2. Render
1. New > Blueprint > choose the repository > Apply. Render asks for four values:
   - `TWOX_ADMIN_USERNAME`: the first admin's username (for example `admin`).
   - `TWOX_ADMIN_PASSWORD`: at least 10 characters. Choose a strong one.
   - `TWOX_CORS_ORIGINS` and `VITE_API_URL`: type a placeholder (`https://placeholder.onrender.com`) for now.
2. Wait for `twox-api` to be Live. Copy its URL and check `<api-url>/health` shows `{"status":"ok"}`.
3. Wait for `twox-web`, then copy its URL.
4. Set the real values:
   - `twox-web` > Environment > `VITE_API_URL` = the API URL (no trailing slash). Save. This is read when the site is built,
     so use **Manual Deploy > Clear build cache & deploy** afterwards.
   - `twox-api` > Environment > `TWOX_CORS_ORIGINS` = the website URL (https, no trailing slash). Save; it redeploys.
5. Open the website URL and sign in with the admin account.

## 3. First use
1. Sign in as admin > Users > create at least one **assessor** and one **verifier** with temporary passwords.
2. Ask each person to sign in and change their password under their name > My account.
3. Assessor: New assessment. Verifier: Evidence review. Admin: Users.

## Roles
| Role | Can do |
|---|---|
| Assessor | Enter assessments; mark evidence as Not provided or Provided. View records. |
| Verifier | Review evidence and mark it Verified, Pending or Rejected (this re-runs the rules). View records. |
| Admin | Manage users. Also enter and review assessments, but cannot review one they created. |

Nobody can mark evidence Verified when creating an assessment, and nobody can verify their own assessment
(set `TWOX_ALLOW_SELF_VERIFY=true` on the API only if a very small team needs it). Every evidence review is logged
with who, when and a note.

## Things to know
- **Persistence:** SQLite lives on the API's disk (`/var/data/twox.db`), which needs a paid plan. Back it up regularly
  (Render disk snapshots). For many users, move to PostgreSQL.
- **Lock-out:** five wrong passwords lock a username for 15 minutes. An admin can reset a password under Users.
- **Lost admin password:** create a second admin account as a precaution. Any admin can reset another user's password under Users.
- **Sessions** last 8 hours (`TWOX_TOKEN_HOURS`) and end when the browser tab closes.
- **Older records** created before login was added show no "created by" and can be reviewed by any verifier.
- Dependencies are unpinned. After it works, run `pip freeze` and `npm ls` and pin versions.

## Run locally
    pip install -r requirements.txt
    set TWOX_ADMIN_USERNAME=admin  and  TWOX_ADMIN_PASSWORD=choose-a-long-password   (use export on Mac/Linux)
    uvicorn backend.main:app --reload
    cd web && npm install && npm run dev      # http://localhost:5173

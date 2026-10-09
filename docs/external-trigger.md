# Morning trigger via cron-job.org

GitHub starts scheduled workflows late, often by hours. So the daily pipeline is started at
05:00 IST by an external cron (cron-job.org, free) that calls GitHub's `workflow_dispatch` API.
GitHub's own cron (`37 23 * * *` = 05:07 IST) stays as a fallback.

Both triggers run with `mode=scheduled`, which adds `--once-per-day`. Whichever trigger arrives
second finds a successful daily run for that IST date and writes and posts nothing. The runs are
queued, never parallel (`concurrency: daily-pipeline`).

What a morning run does:

- It uses the previous day's complete prices; forecasts are keyed by that as-of date.
- The channel post goes out around 05:30–06:00 IST.
- Telegram broadcasts sent before 06:00 IST are silent (`disable_notification`, quiet hours
  21:00–06:00 IST).
- On Sunday (IST) the run also retrains, registers models and runs the price gate. It also runs
  the move challenger's live check, the drift report and the weekly summary.
- On the 1st (IST) it also archives.

## 1. Create a fine-grained personal access token (GitHub)

1. GitHub → avatar → **Settings** → **Developer settings** → **Personal access tokens** →
   **Fine-grained tokens** → **Generate new token**.
2. **Token name:** `cropcast-cron-job-org`. **Expiration:** 1 year, and put a reminder in your
   calendar to rotate it.
3. **Resource owner:** `sayandp`.
4. **Repository access:** **Only select repositories** → `sayandp/kerala-crop-forecaster`.
5. **Permissions → Repository permissions:** **Actions: Read and write**. Leave everything else at
   *No access*. GitHub adds **Metadata: Read-only** automatically; that is expected.
6. **Generate token** and copy it. It is shown only once.

Optional local check: put `GITHUB_DISPATCH_TOKEN=<token>` in `.env` (never committed), run
`uv run python scripts/trigger_daily.py`, and expect `dispatched`. A run then appears under
Actions → daily-pipeline. It does nothing if today's run already succeeded.

## 2. Create the cron job (cron-job.org)

1. Sign up at <https://cron-job.org> (free) → **Create cronjob**.
2. **Title:** `cropcast daily (05:00 IST)`.
3. **URL:**
   `https://api.github.com/repos/sayandp/kerala-crop-forecaster/actions/workflows/daily_pipeline.yml/dispatches`
4. **Execution schedule:** *Every day* at **05:00**. Set the job's time zone to
   **Asia/Kolkata**: in the job's settings, or in account settings if your account defaults to
   another zone.
5. **Advanced** tab:
   - **Request method:** `POST`
   - **Headers** (four entries):
     - `Authorization`: `Bearer <your token>`
     - `Accept`: `application/vnd.github+json`
     - `X-GitHub-Api-Version`: `2022-11-28`
     - `Content-Type`: `application/json`
   - **Request body:** `{"ref":"main","inputs":{"mode":"scheduled"}}`
   - **Treat redirects / success:** GitHub answers **204 No Content**, which cron-job.org counts
     as a success.
   - **Notifications:** turn on *notify on failure* (email).
6. Save, then use **Test run**. Expect HTTP 204 and a new daily-pipeline run on GitHub.

Running `uv run python scripts/trigger_daily.py --show` prints the exact request.

## Troubleshooting

| Symptom | Cause |
|---|---|
| 401 / 403 | Token expired, wrong repository, or Actions permission is not *Read and write* |
| 404 | Wrong URL, or the token cannot see the repository |
| 422 | `ref` or `inputs` wrong: the body must be exactly the JSON above |
| Run says `skipped` | Correct: today's daily run had already succeeded |

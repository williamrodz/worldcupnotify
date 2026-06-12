# adidas Home of Soccer — Ticket Monitor

Checks https://www.adidashomeofsoccer.com/ every hour via GitHub Actions and
pushes a notification to your iPhone via ntfy.sh when the page changes.

## Setup (~5 minutes)

### 1. iPhone notifications (ntfy)
1. Install **ntfy** from the App Store (free).
2. Open it → Subscribe to topic → enter a hard-to-guess topic name, e.g.
   `william-hos-tickets-x7k2q`. (Topics are public — anyone who knows the
   name can see/send messages, so make it random.)
3. In iOS Settings → ntfy → enable notifications. In the app, consider
   enabling "instant delivery" if offered.

### 2. GitHub repo
1. Create a **private** repo (e.g. `site-monitor`).
2. Upload these files keeping the structure:
   - `monitor.py`
   - `.github/workflows/monitor.yml`
3. Repo → Settings → Secrets and variables → Actions → **New repository
   secret**: name `NTFY_TOPIC`, value = your topic name from step 1.

### 3. Test it
1. Repo → Actions tab → "Site Monitor" → **Run workflow**.
2. First run saves a baseline (no notification). Run it a second time to
   confirm "No change." appears in the logs.
3. To test the notification end-to-end, run from any terminal:
   `curl -d "test" ntfy.sh/YOUR_TOPIC_NAME` — your phone should buzz.

That's it. It now runs hourly forever, free.

## Notes & gotchas
- **GitHub cron is not exact.** Scheduled runs can be delayed 5–30 min during
  busy periods. The workflow is set to minute :07 to reduce this. If timing is
  critical near the expected drop date, temporarily change the cron to
  `*/15 * * * *` (every 15 min).
- **The site is a JavaScript app (InEvent platform).** The script hashes the
  served HTML after stripping volatile tokens/timestamps. This catches
  deployments and shell changes, which usually accompany registration
  opening. If you want to be bulletproof: open the site in Chrome, DevTools →
  Network → filter `api.inevent.com`, find the request that returns the
  event/ticket data, and we can point the monitor at that JSON endpoint
  instead — a much cleaner change signal.
- **Free tier:** private repos get 2,000 Actions minutes/month. Each run takes
  ~30s, so hourly checks use ~360 min/month. Every 15 min would use ~1,440 —
  still within the free tier. (Public repos are unlimited, but keep this
  private since your topic name is semi-sensitive.)
- The workflow commits the latest hash + snapshot to `state/` so each run can
  compare against the previous one. `last_snapshot.html` also lets you diff
  exactly what changed after an alert fires.

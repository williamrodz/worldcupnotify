# adidas Home of Soccer — Ticket Monitor (API edition)

Watches the InEvent API behind https://www.adidashomeofsoccer.com/ (eventID
88244) every hour via GitHub Actions and pushes an iPhone notification via
ntfy.sh the moment registration state changes.

## What it watches
1. **Hot flags** (max-priority "🎟️ TICKETS LIKELY LIVE" alert):
   - `event.tool.get` → `registration` (currently "0")
   - `event.tab.find` → "My Tickets" tab visibility (currently "0")
   - `ticket.find` → endpoint status/ticket count (currently errors with 400;
     if it ever returns real ticket data, you'll know immediately, including
     ticket names and prices in the notification)
2. **Other watched flags** (high-priority alert with exact field diff):
   `requiresInvite`, `requiresTicket`, `hideSoldOutTickets`, `allowsWaitlist`,
   `giveawayTicket`, plus visibility of itinerary/forms tabs.
3. **Anything else** in the two public payloads (default-priority alert via
   full payload hash).

## Setup (~5 minutes)
1. **ntfy**: install the ntfy iOS app → subscribe to a random topic name,
   e.g. `william-hos-x7k2q`. Topics are public to anyone who knows the name,
   so keep it unguessable.
2. **GitHub**: create a private repo, upload `monitor.py` and
   `.github/workflows/monitor.yml` (keep the folder structure). Add a repo
   secret `NTFY_TOPIC` = your topic name
   (Settings → Secrets and variables → Actions).
3. **Test**: Actions tab → "Site Monitor" → Run workflow. First run saves a
   baseline. Test your phone with: `curl -d "test" ntfy.sh/YOUR_TOPIC`

## Notes
- GitHub cron can lag 5–30 min. If you learn the approximate drop date,
  change the cron in monitor.yml to `*/15 * * * *` (every 15 min) — still
  free (~30s/run, well under the 2,000 free minutes/month for private repos).
- State and full API payloads are committed to `state/` each run, so after
  any alert you can diff `last_tool.json` / `last_tabs.json` against git
  history to see exactly what changed.
- If InEvent ever requires auth on these endpoints, the monitor will alert
  you with the changed status code rather than failing silently.

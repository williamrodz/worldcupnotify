#!/usr/bin/env python3
"""
Monitors the adidas Home of Soccer event (InEvent eventID 88244) via the
public InEvent API instead of scraping HTML.

Four layers of detection, in order of signal strength:

1. KEY FLAGS — specific fields that almost certainly flip when
   registration/tickets open:
     - event.tool.get -> "registration"        (currently "0")
     - event.tool.get -> "requiresInvite"      (currently "0")
     - event.tool.get -> "hideSoldOutTickets"  (currently "0")
     - event.tab.find -> ticketManager tab "visible" (currently "0")

2. TICKET ENDPOINT STATUS — ticket.find currently returns an error
   (400, "attribute is a required parameter"). If its status/shape ever
   changes (e.g. starts returning ticket data), that's a strong signal.

3. FULL PAYLOAD HASH — any other change in either public endpoint
   triggers a lower-priority "something changed" alert with a field diff.

4. TICKET TEASER IMAGE — the homepage currently shows a "tickets coming
   soon" graphic (an <img> inside <section id="i5dj">) whose CDN filename
   is itself a content hash. If that image's src changes or the image
   disappears, that's a strong signal tickets have gone live.

State is stored in state/ and committed back to the repo by the workflow.
"""

import hashlib
import json
import os
import re
import sys
import urllib.request
import urllib.error

EVENT_ID = "88244"
BASE = "https://api.inevent.com/"
COMMON = f"eventID={EVENT_ID}&version=2&format=json&timezone=America%2FNew_York&lang=en"

ENDPOINTS = {
    "tool": f"{BASE}?action=event.tool.get&{COMMON}",
    "tabs": f"{BASE}?action=event.tab.find&type=web&displayInvisible=1&{COMMON}",
}
TICKET_URL = f"{BASE}?action=ticket.find&listing=1&paginated=0&limit=100&{COMMON}"

SITE_URL = "https://www.adidashomeofsoccer.com/"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
STATE_FILE = "state/api_state.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def fetch_json(url: str) -> dict:
    """Fetch a URL, returning {'status': int, 'body': parsed-or-raw}."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        status = e.code
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        body = {"_raw": raw[:2000]}
    return {"status": status, "body": body}


def fetch_html(url: str) -> str:
    """Fetch a URL, returning its decoded HTML body (even on HTTP errors)."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.read().decode("utf-8", errors="replace")


# The "tickets coming soon" teaser image sits in <section id="i5dj"> as the
# first element in <body>. Its CDN filename is a content hash, so any swap
# or removal of this image is a strong "tickets may be live" signal.
TICKET_IMAGE_SECTION_RE = re.compile(
    r'<section[^>]*\bid="i5dj"[^>]*>(.*?)</section>', re.IGNORECASE | re.DOTALL
)
IMG_SRC_RE = re.compile(r'<img\b[^>]*\bsrc="([^"]+)"', re.IGNORECASE)


def extract_ticket_image_src(html: str) -> str | None:
    """Return the src of the ticket teaser image, or None if not found."""
    section = TICKET_IMAGE_SECTION_RE.search(html)
    container = section.group(1) if section else html[:2000]
    img = IMG_SRC_RE.search(container)
    return img.group(1) if img else None


def extract_signals(tool: dict, tabs: dict, ticket: dict) -> dict:
    """Pull out the specific fields we care most about."""
    signals = {}
    try:
        d = tool["body"]["data"][0]
        for key in ("registration", "requiresInvite", "requiresTicket",
                    "hideSoldOutTickets", "allowsWaitlist", "giveawayTicket"):
            signals[f"tool.{key}"] = d.get(key)
    except (KeyError, IndexError, TypeError):
        signals["tool._error"] = "unexpected response shape"

    try:
        for tab in tabs["body"]["data"]:
            if tab.get("tab") in ("ticketManager", "myItinerary", "myForms"):
                signals[f"tab.{tab['tab']}.visible"] = tab.get("visible")
    except (KeyError, TypeError):
        signals["tabs._error"] = "unexpected response shape"

    # Ticket endpoint: status code + error message (or count if it works)
    signals["ticket.status"] = ticket["status"]
    body = ticket["body"]
    if isinstance(body, dict):
        if "error" in body:
            signals["ticket.error"] = body["error"].get("message")
        if "count" in body:
            signals["ticket.count"] = body["count"]
            # If we ever get actual ticket data, capture names/availability
            try:
                signals["ticket.items"] = [
                    {k: t.get(k) for k in ("name", "available", "quantity",
                                           "price", "soldOut") if k in t}
                    for t in body.get("data", [])
                ]
            except (TypeError, AttributeError):
                pass
    return signals


def payload_hash(tool: dict, tabs: dict) -> str:
    blob = json.dumps({"tool": tool["body"], "tabs": tabs["body"]},
                      sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def diff_signals(old: dict, new: dict) -> list[str]:
    changes = []
    for key in sorted(set(old) | set(new)):
        if old.get(key) != new.get(key):
            changes.append(f"{key}: {old.get(key)!r} -> {new.get(key)!r}")
    return changes


def notify(title: str, message: str, priority: str = "urgent") -> None:
    if not NTFY_TOPIC:
        print("WARNING: NTFY_TOPIC not set, skipping notification")
        return
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={"Title": title, "Priority": priority,
                 "Tags": "soccer,rotating_light", "Click": SITE_URL},
    )
    urllib.request.urlopen(req, timeout=30)
    print(f"Notification sent: {title}")


# Flags whose change means "GO NOW" (max priority)
HOT_KEYS = ("tool.registration", "tab.ticketManager.visible",
            "ticket.status", "ticket.count", "page.ticket_image_src")


def main() -> None:
    tool = fetch_json(ENDPOINTS["tool"])
    tabs = fetch_json(ENDPOINTS["tabs"])
    ticket = fetch_json(TICKET_URL)
    homepage = fetch_html(SITE_URL)

    new_signals = extract_signals(tool, tabs, ticket)
    new_signals["page.ticket_image_src"] = extract_ticket_image_src(homepage)
    new_hash = payload_hash(tool, tabs)
    print("Signals:", json.dumps(new_signals, indent=2)[:1500])
    print("Payload hash:", new_hash)

    old = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            old = json.load(f)

    os.makedirs("state", exist_ok=True)

    if not old:
        print("First run — saving baseline, no notification.")
    else:
        changes = diff_signals(old.get("signals", {}), new_signals)
        hot = [c for c in changes
               if any(c.startswith(k + ":") for k in HOT_KEYS)]
        if hot:
            notify(
                "🎟️ TICKETS LIKELY LIVE — Home of Soccer",
                "Key signals changed:\n" + "\n".join(hot)
                + f"\n\nGo: {SITE_URL}",
                priority="max",
            )
        elif changes:
            notify(
                "👀 Home of Soccer event config changed",
                "\n".join(changes[:15]) + f"\n\nCheck: {SITE_URL}",
                priority="high",
            )
        elif new_hash != old.get("hash"):
            notify(
                "ℹ️ Home of Soccer API payload changed",
                f"No key flags flipped, but the event data changed. "
                f"Worth a look: {SITE_URL}",
                priority="default",
            )
        else:
            print("No change.")

    with open(STATE_FILE, "w") as f:
        json.dump({"signals": new_signals, "hash": new_hash}, f, indent=2)
    # Keep full payloads for post-alert diffing
    with open("state/last_tool.json", "w") as f:
        json.dump(tool["body"], f, indent=2, sort_keys=True)
    with open("state/last_tabs.json", "w") as f:
        json.dump(tabs["body"], f, indent=2, sort_keys=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        try:
            notify("⚠️ Site monitor error", str(e), priority="default")
        except Exception:
            pass
        sys.exit(1)

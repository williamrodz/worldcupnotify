#!/usr/bin/env python3
"""
Monitors https://www.adidashomeofsoccer.com/ for changes.
On change: sends a push notification via ntfy.sh and updates the stored state.

State (last hash + last snapshot) is committed back to the repo by the
GitHub Actions workflow, so it persists between runs.
"""

import hashlib
import os
import re
import sys
import urllib.request

URL = "https://www.adidashomeofsoccer.com/"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")  # set as a GitHub secret
STATE_FILE = "state/last_hash.txt"
SNAPSHOT_FILE = "state/last_snapshot.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
}


def fetch_page() -> str:
    req = urllib.request.Request(URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def normalize(html: str) -> str:
    """Strip content that changes on every request so we only
    detect *meaningful* changes."""
    # Remove CSRF / session-ish tokens, nonces, long hex/base64 blobs
    html = re.sub(r'(csrf|token|nonce|session)[^"\']{0,20}["\'][^"\']+["\']',
                  "", html, flags=re.IGNORECASE)
    # Remove inline timestamps / cache-busting query strings
    html = re.sub(r"[?&](v|ver|t|ts|cb|_)=[\w.-]+", "", html)
    html = re.sub(r"\b\d{10,13}\b", "", html)  # unix timestamps
    # Collapse whitespace
    html = re.sub(r"\s+", " ", html)
    return html.strip()


def notify(title: str, message: str, priority: str = "urgent") -> None:
    if not NTFY_TOPIC:
        print("WARNING: NTFY_TOPIC not set, skipping notification")
        return
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            "Title": title,
            "Priority": priority,
            "Tags": "soccer,rotating_light",
            "Click": URL,
        },
    )
    urllib.request.urlopen(req, timeout=30)
    print(f"Notification sent: {title}")


def main() -> None:
    html = fetch_page()
    normalized = normalize(html)
    new_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    print(f"Current hash: {new_hash}")

    old_hash = None
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            old_hash = f.read().strip()
        print(f"Previous hash: {old_hash}")

    os.makedirs("state", exist_ok=True)

    if old_hash is None:
        # First run: just record baseline
        print("First run — saving baseline, no notification.")
    elif new_hash != old_hash:
        print("CHANGE DETECTED!")
        notify(
            "🚨 adidas Home of Soccer changed!",
            f"The site has changed — tickets may be live. Check now: {URL}",
        )
    else:
        print("No change.")

    with open(STATE_FILE, "w") as f:
        f.write(new_hash)
    with open(SNAPSHOT_FILE, "w") as f:
        f.write(html)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        # Optional: get notified if the checker itself breaks
        try:
            notify("⚠️ Site monitor error", str(e), priority="default")
        except Exception:
            pass
        sys.exit(1)

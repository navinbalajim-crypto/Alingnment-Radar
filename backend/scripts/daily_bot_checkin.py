"""Daily keep-alive and active engagement script for Alignment Radar.
Logs into the live application as `radar_bot`, sends a check-in message,
and maintains an active session for 30 seconds.
"""

import sys
import time
from datetime import datetime
import httpx

BASE_URL = "https://alingnment-radar.onrender.com/api/v1"
HEALTH_URL = "https://alingnment-radar.onrender.com/health"
BOT_USER = "radar_bot"
BOT_PASSWORD = "RadarBot@2026"
TARGET_RECIPIENT = "navinbalajim"


def run_checkin():
    print(f"[{datetime.now().isoformat()}] Starting Alignment Radar daily check-in...")

    # 1. Ping health check (wakes up backend if Render is sleeping)
    print("Pinging health endpoint...")
    try:
        r = httpx.get(HEALTH_URL, timeout=60.0)
        print(f"Health check status: {r.status_code}")
    except Exception as e:
        print(f"Health check notice: {e}")

    # 2. Login as radar_bot
    print(f"Logging in as {BOT_USER}...")
    try:
        r = httpx.post(
            f"{BASE_URL}/auth/login/password",
            json={"username": BOT_USER, "password": BOT_PASSWORD},
            timeout=45.0,
        )
        if r.status_code != 200:
            print(f"Login failed ({r.status_code}): {r.text}")
            return False
        data = r.json()
        token = data.get("access_token")
        if not token:
            print("No access token returned.")
            return False
        print("Logged in successfully.")
    except Exception as e:
        print(f"Login request failed: {e}")
        return False

    headers = {"Authorization": f"Bearer {token}"}

    # 3. Get or create direct conversation with target recipient
    print(f"Opening direct chat with @{TARGET_RECIPIENT}...")
    try:
        r_conv = httpx.post(
            f"{BASE_URL}/conversations/direct/{TARGET_RECIPIENT}",
            headers=headers,
            timeout=30.0,
        )
        if r_conv.status_code not in (200, 201):
            print(f"Could not open conversation ({r_conv.status_code}): {r_conv.text}")
            return False
        conv_id = r_conv.json().get("id")
        print(f"Conversation ready (ID: {conv_id}).")
    except Exception as e:
        print(f"Conversation request failed: {e}")
        return False

    # 4. Send keep-alive message
    now_str = datetime.now().strftime("%Y-%m-%d %I:%M %p")
    message_text = f"🤖 Daily Check-in ({now_str}): Alignment Radar is live, healthy, and operational!"
    print("Sending daily message...")
    try:
        r_msg = httpx.post(
            f"{BASE_URL}/conversations/{conv_id}/messages",
            json={"content": message_text, "message_type": "text"},
            headers=headers,
            timeout=30.0,
        )
        if r_msg.status_code not in (200, 201):
            print(f"Message send failed ({r_msg.status_code}): {r_msg.text}")
            return False
        print(f"Message sent successfully! (ID: {r_msg.json().get('id')})")
    except Exception as e:
        print(f"Message request failed: {e}")
        return False

    # 5. Maintain active session for 30 seconds
    print("Maintaining active session for 30 seconds as requested...")
    for remaining in range(30, 0, -10):
        print(f"Active in app... {remaining}s remaining")
        time.sleep(10)

    print(f"[{datetime.now().isoformat()}] Daily check-in complete!")
    return True


if __name__ == "__main__":
    success = run_checkin()
    sys.exit(0 if success else 1)

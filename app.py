import os
import time
import threading
import requests
import pytchat
from flask import Flask

app = Flask(__name__)

ACCESS_TOKEN = os.getenv("YOUTUBE_ACCESS_TOKEN")
REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")
CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
VIDEO_ID = os.getenv("YOUTUBE_VIDEO_ID")

access_token_lock = threading.Lock()

def refresh_access_token():
    global ACCESS_TOKEN
    url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token"
    }
    response = requests.post(url, data=data)
    if response.status_code == 200:
        new_token = response.json()["access_token"]
        with access_token_lock:
            ACCESS_TOKEN = new_token
        print("✅ Access token refreshed.")
    else:
        print("❌ Failed to refresh token:", response.text)

def token_refresher():
    while True:
        refresh_access_token()
        # Refresh every 50 minutes (tokens usually last 1 hour)
        time.sleep(50 * 60)

def send_message(video_id, message_text):
    with access_token_lock:
        token = ACCESS_TOKEN

    url = "https://youtube.googleapis.com/youtube/v3/liveChat/messages?part=snippet"

    video_info = requests.get(
        f"https://www.googleapis.com/youtube/v3/videos?part=liveStreamingDetails&id={video_id}",
        headers={"Authorization": f"Bearer {token}"}
    )

    if video_info.status_code != 200:
        print("❌ Failed to get video info. Trying token refresh.")
        refresh_access_token()
        return

    live_chat_id = video_info.json()["items"][0]["liveStreamingDetails"]["activeLiveChatId"]

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "snippet": {
            "liveChatId": live_chat_id,
            "type": "textMessageEvent",
            "textMessageDetails": {
                "messageText": message_text
            }
        }
    }

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 401:
        print("🔁 Token expired. Refreshing...")
        refresh_access_token()
        send_message(video_id, message_text)  # Retry once with new token
    elif response.status_code == 200:
        print(f"✅ Replied: {message_text}")
    else:
        print("❌ Failed to send message:", response.text)

def run_bot():
    if not VIDEO_ID:
        print("❌ Error: YOUTUBE_VIDEO_ID environment variable not set.")
        return

    chat = pytchat.create(video_id=VIDEO_ID)
    print("✅ Bot started...")

    while chat.is_alive():
        for c in chat.get().sync_items():
            print(f"{c.author.name}: {c.message}")
            if "!hello" in c.message.lower():
                reply = f"Hi {c.author.name}!"
                send_message(VIDEO_ID, reply)
        time.sleep(1)

@app.route("/")
def home():
    return "🤖 YouTube Bot is running!"

def start_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    # Start token refresher thread (daemon so it stops with main thread)
    threading.Thread(target=token_refresher, daemon=True).start()
    threading.Thread(target=start_flask, daemon=True).start()
    run_bot()

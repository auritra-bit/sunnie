import os
import time
import threading
import requests
import pytchat
from flask import Flask

app = Flask(__name__)

# Get env vars from Render
ACCESS_TOKEN = os.getenv("YOUTUBE_ACCESS_TOKEN")
REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")
CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
VIDEO_ID = os.getenv("YOUTUBE_VIDEO_ID")

# Refresh token function
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
        ACCESS_TOKEN = response.json()["access_token"]
        print("✅ Access token refreshed.")
    else:
        print("❌ Failed to refresh token:", response.text)

# Send reply to YouTube live chat
def send_message(video_id, message_text, access_token):
    url = "https://youtube.googleapis.com/youtube/v3/liveChat/messages?part=snippet"
    
    # Get liveChatId for the video
    video_info = requests.get(
        f"https://www.googleapis.com/youtube/v3/videos?part=liveStreamingDetails&id={video_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    if video_info.status_code != 200:
        print("❌ Failed to get video info. Trying token refresh.")
        refresh_access_token()
        return

    live_chat_id = video_info.json()["items"][0]["liveStreamingDetails"]["activeLiveChatId"]

    headers = {
        "Authorization": f"Bearer {access_token}",
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
        send_message(video_id, message_text, ACCESS_TOKEN)
    elif response.status_code == 200:
        print(f"✅ Replied: {message_text}")
    else:
        print("❌ Failed to send message:", response.text)

# Main bot logic
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
                send_message(VIDEO_ID, reply, ACCESS_TOKEN)

        time.sleep(1)

# Flask route to show bot is live
@app.route("/")
def home():
    return "🤖 YouTube Bot is running!"

# Start bot and Flask
if __name__ == "__main__":
    # Run bot in background thread
    threading.Thread(target=run_bot, daemon=True).start()

    # Start Flask app (Render looks for port)
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

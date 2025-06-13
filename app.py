import pytchat
import requests
import time
import os

# ENV values
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# Get new access token using refresh token
def get_access_token():
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
    )
    return response.json().get("access_token")

# Send reply to chat
def send_message(live_chat_id, message, access_token):
    url = "https://www.googleapis.com/youtube/v3/liveChat/messages?part=snippet"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "snippet": {
            "liveChatId": live_chat_id,
            "type": "textMessageEvent",
            "textMessageDetails": {
                "messageText": message
            }
        }
    }
    res = requests.post(url, headers=headers, json=payload)
    print("Sent:", res.status_code, res.text)

# --- Start Bot ---
video_id = "YOUR_STREAM_ID"  # change this
chat = pytchat.create(video_id=video_id)
print("Bot started...")

while chat.is_alive():
    for c in chat.get().sync_items():
        print(f"{c.author.name}: {c.message}")
        if c.message.lower() == "!hello":
            token = get_access_token()
            send_message(c.live_chat_id, f"Hi {c.author.name}!", token)
    time.sleep(1)
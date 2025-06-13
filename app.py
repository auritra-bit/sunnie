from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "Sunnie-BOT is running!"

import pytchat
import requests
import time
import os

REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
VIDEO_ID = os.getenv("VIDEO_ID")

def get_access_token():
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": REFRESH_TOKEN,
            "grant_type": "refresh_token"
        }
    )
    return response.json().get("access_token")

def send_message(live_chat_id, message, access_token):
    url = "https://www.googleapis.com/youtube/v3/liveChat/messages?part=snippet"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
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
    print("Message Sent:", res.status_code)

def your_bot_function_name():
    chat = pytchat.create(video_id=VIDEO_ID)
    print("Bot started...")
    while chat.is_alive():
        for c in chat.get().sync_items():
            print(f"{c.author.name}: {c.message}")
            if c.message.lower() == "!hello":
                token = get_access_token()
                send_message(c.live_chat_id, f"Hi {c.author.name}!", token)
        time.sleep(1)

def run_flask():
    app.run(host='0.0.0.0', port=10000)

# ✅ Run Flask in a thread, and bot on main thread
threading.Thread(target=run_flask).start()
your_bot_function_name()

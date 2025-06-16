import os
import time
import threading
import requests
import pytchat
import json
from flask import Flask
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import re
from collections import defaultdict

app = Flask(__name__)

# Load credentials from environment variable
VIDEO_ID = os.getenv("YOUTUBE_VIDEO_ID")
credentials = json.loads(os.getenv("PROJECTS_JSON", "[]"))
current_index = 0
ACCESS_TOKEN = None  # Will be generated using refresh token

# === Google Sheet Setup ===
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "/etc/secrets/credentials.json")
scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]

# Reminder system variables
active_reminders = []
reminder_threads = []

# Study buddy system variables
buddy_requests = {}
active_buddies = {}

# Add these lines with other global variables
active_pomodoros = {}  # Store active pomodoro sessions by user ID
pomodoro_threads = []  # Store pomodoro thread references

# Initialize Google Sheets client
try:
    client = gspread.service_account(filename=SERVICE_ACCOUNT_FILE)
    spreadsheet = client.open("StudyPlusData")
    
    # Define separate sheets
    attendance_sheet = spreadsheet.worksheet("attendance")
    session_sheet = spreadsheet.worksheet("session") 
    task_sheet = spreadsheet.worksheet("task")
    xp_sheet = spreadsheet.worksheet("xp")
    
    # Add goal sheet - make sure this sheet exists in your Google Sheet
    try:
        goal_sheet = spreadsheet.worksheet("goal")
    except:
        # If goal sheet doesn't exist, create it
        goal_sheet = spreadsheet.add_worksheet(title="goal", rows="1000", cols="6")
        goal_sheet.append_row(["Username", "UserID", "GoalName", "CreatedDate", "CompletedDate", "Status"])
    
    SHEETS_ENABLED = True
    print("✅ Google Sheets connected successfully")
except Exception as e:
    print(f"❌ Google Sheets connection failed: {e}")
    SHEETS_ENABLED = False

# === Timer Message System ===
# Global variables for tracking
chat_message_count = 0
last_reset_time = datetime.now()
timer_threads = []

# Timer messages configuration
TIMER_MESSAGES = [
    {
        "message": "To study more attentively and productively, use commands. Type !help to see all commands. Learn how to use them here: https://tinyurl.com/command-user-manual —Use it to make your study more efficient",
        "interval_minutes": 20,
        "min_chat_lines": 5,
        "last_sent": None
    },
    {
        "message": "Hi guys! I am Sunnie — a former public servant at the Ministry of National Defense, now studying to become an IT official. More about me & the stream: https://tinyurl.com/sunnie-study",
        "interval_minutes": 40,
        "min_chat_lines": 3,
        "last_sent": None
    },
    {
        "message": "If you want to study with me, do not forget to subscribe and like 😊 If you like to support the live stream: https://buymeacoffee.com/nayakwonelq -Happy studying and thank you 💛",
        "interval_minutes": 55,
        "min_chat_lines": 6,
        "last_sent": None
    },
    {
        "message": "Chat Rules: Be respectful, no ads/spam/explicit content. Please use English only for chat. Follow moderators. Respect everyone. Spamming, insults, or harassment will lead to a ban",
        "interval_minutes": 30,
        "min_chat_lines": 7,
        "last_sent": None
    },
    {
        "message": "I usually start my live stream between 10:00 AM and 2:00 AM KST and study for 7 to 10 hours. Any schedule changes due to unforeseen events will be updated instantly via a post on the YT Community tab",
        "interval_minutes": 40,
        "min_chat_lines": 4,
        "last_sent": None
    },
]

def increment_chat_count():
    """Call this function every time a new chat message is received"""
    global chat_message_count
    chat_message_count += 1

def reset_chat_count_daily():
    """Reset chat count every 24 hours"""
    global chat_message_count, last_reset_time
    
    while True:
        now = datetime.now()
        if now - last_reset_time >= timedelta(days=1):
            chat_message_count = 0
            last_reset_time = now
            print("📊 Daily chat count reset")
        
        time.sleep(3600)  # Check every hour

def should_send_timer_message(timer_config):
    """Check if a timer message should be sent"""
    global chat_message_count
    
    now = datetime.now()
    
    # Check if enough chat lines have occurred
    if chat_message_count < timer_config["min_chat_lines"]:
        return False
    
    # Check if enough time has passed since last message of this type
    if timer_config["last_sent"] is None:
        return True
    
    time_diff = now - timer_config["last_sent"]
    required_interval = timedelta(minutes=timer_config["interval_minutes"])
    
    return time_diff >= required_interval

def send_timer_message(timer_config):
    """Send a timer message and update its last_sent time"""
    global chat_message_count
    
    try:
        send_message(VIDEO_ID, timer_config["message"], ACCESS_TOKEN)
        timer_config["last_sent"] = datetime.now()
        
        # Reset chat count after sending message
        chat_message_count = 0
        
        print(f"📢 Timer message sent: {timer_config['message'][:50]}...")
    except Exception as e:
        print(f"❌ Error sending timer message: {e}")

def timer_message_worker():
    """Background worker to check and send timer messages"""
    while True:
        try:
            for timer_config in TIMER_MESSAGES:
                if should_send_timer_message(timer_config):
                    send_timer_message(timer_config)
                    time.sleep(2)  # Small delay between messages if multiple are due
        except Exception as e:
            print(f"❌ Timer message worker error: {e}")
        
        time.sleep(60)  # Check every minute

def start_timer_system():
    """Initialize and start the timer message system"""
    # Start daily reset thread
    reset_thread = threading.Thread(target=reset_chat_count_daily, daemon=True)
    reset_thread.start()
    timer_threads.append(reset_thread)
    
    # Start timer message worker thread
    timer_thread = threading.Thread(target=timer_message_worker, daemon=True)
    timer_thread.start()
    timer_threads.append(timer_thread)
    
    print("✅ Timer message system started")

def refresh_access_token_auto():
    global ACCESS_TOKEN, current_index

    for _ in range(len(credentials)):
        cred = credentials[current_index]
        data = {
            "client_id": cred["client_id"],
            "client_secret": cred["client_secret"],
            "refresh_token": cred["refresh_token"],
            "grant_type": "refresh_token"
        }
        response = requests.post("https://oauth2.googleapis.com/token", data=data)
        if response.status_code == 200:
            ACCESS_TOKEN = response.json()["access_token"]
            print(f"✅ Access token refreshed from: {cred['name']}")
            return
        else:
            print(f"❌ Failed to refresh from {cred['name']}, trying next...")
            current_index = (current_index + 1) % len(credentials)

    print("❌ All tokens failed.")
    ACCESS_TOKEN = None

def send_message(video_id, message_text, access_token):
    url = "https://youtube.googleapis.com/youtube/v3/liveChat/messages?part=snippet"

    video_info = requests.get(
        f"https://www.googleapis.com/youtube/v3/videos?part=liveStreamingDetails&id={video_id}",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    if video_info.status_code != 200:
        print("❌ Failed to get video info. Trying token refresh.")
        refresh_access_token_auto()
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

# === Helper Functions ===
def update_user_xp(username, userid, xp_earned, action_type):
    """Update or create user XP record in the xp sheet"""
    if not SHEETS_ENABLED:
        return
    
    try:
        records = xp_sheet.get_all_records()
        user_found = False
        
        for i, row in enumerate(records):
            if str(row['UserID']) == str(userid):
                # Update existing user
                current_xp = int(row.get('TotalXP', 0))
                new_total = current_xp + int(xp_earned)
                xp_sheet.update_cell(i + 2, 3, new_total)  # TotalXP column
                xp_sheet.update_cell(i + 2, 4, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))  # LastUpdated
                user_found = True
                break
        
        if not user_found:
            # Add new user
            xp_sheet.append_row([
                username,
                userid,
                int(xp_earned),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])
    except Exception as e:
        print(f"Error updating XP: {e}")

def get_user_total_xp(userid):
    """Get user's total XP from xp sheet"""
    if not SHEETS_ENABLED:
        return 0
    
    try:
        records = xp_sheet.get_all_records()
        for row in records:
            if str(row['UserID']) == str(userid):
                return int(row.get('TotalXP', 0))
        return 0
    except:
        return 0

def calculate_streak(userid):
    """Calculate daily streak from attendance sheet"""
    if not SHEETS_ENABLED:
        return 0
    
    try:
        records = attendance_sheet.get_all_records()
        dates = set()
        for row in records:
            if str(row['UserID']) == str(userid):
                try:
                    date = datetime.strptime(str(row['Date']), "%Y-%m-%d %H:%M:%S").date()
                    dates.add(date)
                except ValueError:
                    pass

        if not dates:
            return 0

        streak = 0
        today = datetime.now().date()

        for i in range(0, 365):
            day = today - timedelta(days=i)
            if day in dates:
                streak += 1
            else:
                break
        return streak
    except:
        return 0

def get_rank(xp):
    xp = int(xp)
    if xp >= 20000:
        return "🤴Study Leader of the month"
    elif xp >= 15000:
        return "🥷⚔️Sunnie's Study Café's Ninja"
    elif xp >= 10000:
        return "🌌 Eternal Shadowblade"
    elif xp >= 8000:
        return "🛡️ Legendary Phantom Shinobi"
    elif xp >= 6000:
        return "⚡ Ascended Stealth Slayer"
    elif xp >= 5000:
        return "🔥 Dragonfire Mystic Ninja"
    elif xp >= 4000:
        return "🌪️ Stormborn Silent Tempest"
    elif xp >= 3000:
        return "💥 Shadowblade Ninja"
    elif xp >= 2500:
        return "🔥 Phantom Shinobi"
    elif xp >= 2000:
        return "⚔️ Stealth Slayer"
    elif xp >= 1500:
        return "🐉 Mystic Ninja"
    elif xp >= 1200:
        return "🌀 Silent Tempest"
    elif xp >= 1000:
        return "🌑 Nightcrawler"
    elif xp >= 850:
        return "🎯 Swift Claw"
    elif xp >= 700:
        return "🥷 Ninja Adept"
    elif xp >= 550:
        return "🌪️ Shadow Trainee"
    elif xp >= 400:
        return "💨 Hidden Leafling"
    elif xp >= 300:
        return "🦊 Masked Novice"
    elif xp >= 200:
        return "🔪 Kunai Rookie"
    elif xp >= 120:
        return "🥋 Beltless Initiate"
    elif xp >= 60:
        return "🎒 Scroll Carrier"
    elif xp >= 30:
        return "👣 Silent Steps"
    else:
        return "🍼 Lost in the Mist"

def get_badges(total_minutes):
    badges = []
    if total_minutes >= 30:
        badges.append("🥷 Silent Scroll")
    if total_minutes >= 60:
        badges.append("🗡️ Swift Kunai")
    if total_minutes >= 90:
        badges.append("🌀 Shadow Shuriken")
    if total_minutes >= 120:
        badges.append("🌑 Nightblade")
    if total_minutes >= 180:
        badges.append("⚡ Lightning Step")
    if total_minutes >= 240:
        badges.append("🔥 Fire Lotus")
    if total_minutes >= 300:
        badges.append("🐉 Dragon's Breath")
    if total_minutes >= 420:
        badges.append("🌪️ Tornado Strike")
    if total_minutes >= 600:
        badges.append("🛡️ Phantom Guard")
    if total_minutes >= 800:
        badges.append("💥 Shadow Master")
    if total_minutes >= 1000:
        badges.append("🌌 Eternal Ninja")
    return badges

def parse_reminder_time(text):
    """Parse reminder time from text like '30 min', '2 hour', '45 minutes', etc."""
    text = text.lower().strip()
    
    # Pattern for numbers followed by time units
    patterns = [
        (r'(\d+)\s*(?:min|minute|minutes)', 1),  # minutes
        (r'(\d+)\s*(?:h|hr|hour|hours)', 60),    # hours
        (r'(\d+)\s*(?:sec|second|seconds)', 1/60), # seconds (convert to minutes)
    ]
    
    for pattern, multiplier in patterns:
        match = re.search(pattern, text)
        if match:
            number = int(match.group(1))
            return int(number * multiplier)
    
    return None

def reminder_worker(username, userid, message, delay_minutes):
    """Background worker to send reminder after specified time"""
    try:
        time.sleep(delay_minutes * 60)  # Convert minutes to seconds
        
        # Check if reminder is still active (user might have cancelled)
        global active_reminders
        reminder_key = f"{userid}_{int(time.time())}"
        
        reminder_text = f"⏰ {username}, reminder: {message}" if message else f"⏰ {username}, your {delay_minutes}-minute reminder is up!"
        send_message(VIDEO_ID, reminder_text, ACCESS_TOKEN)
        
        print(f"📢 Reminder sent to {username}: {message}")
        
    except Exception as e:
        print(f"❌ Error in reminder worker: {e}")

def handle_remind(username, userid, remind_text):
    """Handle reminder commands"""
    if not remind_text or len(remind_text.strip()) < 1:
        return f"⚠️ {username}, use: !remind 30 min take tea OR !remind 2 hour study break OR !remind 45 min"
    
    text = remind_text.strip()
    
    # Parse time from the beginning of the text
    delay_minutes = parse_reminder_time(text)
    
    if not delay_minutes:
        return f"⚠️ {username}, I couldn't understand the time. Use: !remind 30 min, !remind 2 hour, etc."
    
    if delay_minutes > 1440:  # More than 24 hours
        return f"⚠️ {username}, reminder time cannot exceed 24 hours."
    
    if delay_minutes < 1:  # Less than 1 minute
        return f"⚠️ {username}, reminder time must be at least 1 minute."
    
    # Extract message (everything after the time part)
    message_match = re.sub(r'\d+\s*(?:min|minute|minutes|h|hr|hour|hours|sec|second|seconds)', '', text, 1).strip()
    
    # Remove common words like "later", "about", "me"
    message_match = re.sub(r'^(?:later|about|me|for|to)\s*', '', message_match).strip()
    
    # Start reminder thread
    reminder_thread = threading.Thread(
        target=reminder_worker, 
        args=(username, userid, message_match, delay_minutes),
        daemon=True
    )
    reminder_thread.start()
    reminder_threads.append(reminder_thread)
    
    time_text = f"{delay_minutes} minute{'s' if delay_minutes != 1 else ''}"
    if delay_minutes >= 60:
        hours = delay_minutes // 60
        mins = delay_minutes % 60
        time_text = f"{hours} hour{'s' if hours != 1 else ''}"
        if mins > 0:
            time_text += f" {mins} minute{'s' if mins != 1 else ''}"
    
    message_part = f" about '{message_match}'" if message_match else ""
    return f"⏰ {username}, reminder set for {time_text}{message_part}!"

# ============== STUDY BUDDY SYSTEM FUNCTIONS ==============

def handle_buddy(username, userid, buddy_command):
    """Handle buddy system commands"""
    global buddy_requests, active_buddies
    
    if not buddy_command:
        # Show buddy status
        if userid in active_buddies:
            buddy_info = active_buddies[userid]
            return f"👥 {username}, you're buddied with {buddy_info['buddy_name']} since {buddy_info['paired_date'][:10]}"
        else:
            return f"👥 {username}, you don't have a study buddy. Use !buddy @username or !buddy find"
    
    command_parts = buddy_command.strip().split()
    action = command_parts[0].lower()
    
    if action == "find":
        return handle_buddy_find(username, userid)
    elif action == "accept":
        return handle_buddy_accept(username, userid)
    elif action == "decline":
        return handle_buddy_decline(username, userid)
    elif action == "remove":
        return handle_buddy_remove(username, userid)
    elif action == "stats":
        return handle_buddy_stats(username, userid)
    elif action.startswith("@") or len(command_parts) > 1:
        # Buddy request to specific user
        target_name = action[1:] if action.startswith("@") else " ".join(command_parts)
        return handle_buddy_request(username, userid, target_name)
    else:
        return f"⚠️ {username}, use: !buddy @username, !buddy find, !buddy accept, !buddy decline, !buddy remove, or !buddy stats"

def handle_buddy_request(username, userid, target_name):
    """Send buddy request to specific user"""
    global buddy_requests, active_buddies
    
    if userid in active_buddies:
        return f"⚠️ {username}, you already have a study buddy! Use !buddy remove first."
    
    # For demo purposes, we'll store requests by username since we don't have user lookup
    request_key = target_name.lower().replace("@", "")
    
    buddy_requests[request_key] = {
        'requester_id': userid,
        'requester_name': username,
        'target_name': target_name,
        'timestamp': datetime.now()
    }
    
    return f"📨 {username}, buddy request sent to {target_name}! They can use !buddy accept to become your study buddy."

def handle_buddy_find(username, userid):
    """Find available study buddies"""
    if userid in active_buddies:
        return f"⚠️ {username}, you already have a study buddy! Use !buddy remove first."
    
    return f"👥 {username}, looking for study buddies! Other users can send you a request with !buddy {username}"

def handle_buddy_accept(username, userid):
    """Accept incoming buddy request"""
    global buddy_requests, active_buddies
    
    if userid in active_buddies:
        return f"⚠️ {username}, you already have a study buddy!"
    
    # Find request for this user
    request_key = username.lower()
    if request_key not in buddy_requests:
        return f"⚠️ {username}, you don't have any pending buddy requests."
    
    request = buddy_requests[request_key]
    requester_id = request['requester_id']
    requester_name = request['requester_name']
    
    # Check if requester already has a buddy
    if requester_id in active_buddies:
        del buddy_requests[request_key]
        return f"⚠️ {username}, {requester_name} already found another study buddy."
    
    # Create buddy pair
    buddy_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    active_buddies[userid] = {
        'buddy_id': requester_id,
        'buddy_name': requester_name,
        'paired_date': buddy_date
    }
    
    active_buddies[requester_id] = {
        'buddy_id': userid,
        'buddy_name': username,
        'paired_date': buddy_date
    }
    
    # Remove the request
    del buddy_requests[request_key]
    
    return f"🤝 {username} and {requester_name} are now study buddies! Use !buddy stats to compare progress."

def handle_buddy_decline(username, userid):
    """Decline incoming buddy request"""
    global buddy_requests
    
    request_key = username.lower()
    if request_key in buddy_requests:
        requester_name = buddy_requests[request_key]['requester_name']
        del buddy_requests[request_key]
        return f"❌ {username}, you declined the buddy request from {requester_name}."
    else:
        return f"⚠️ {username}, you don't have any pending buddy requests."

def handle_buddy_remove(username, userid):
    """Remove current study buddy"""
    global active_buddies
    
    if userid not in active_buddies:
        return f"⚠️ {username}, you don't have a study buddy to remove."
    
    buddy_info = active_buddies[userid]
    buddy_id = buddy_info['buddy_id']
    buddy_name = buddy_info['buddy_name']
    
    # Remove both sides of the buddy relationship
    del active_buddies[userid]
    if buddy_id in active_buddies:
        del active_buddies[buddy_id]
    
    return f"💔 {username}, you're no longer study buddies with {buddy_name}."

def handle_buddy_stats(username, userid):
    """Compare stats with study buddy"""
    global active_buddies
    
    if userid not in active_buddies:
        return f"⚠️ {username}, you don't have a study buddy. Use !buddy find or !buddy @username"
    
    buddy_info = active_buddies[userid]
    buddy_name = buddy_info['buddy_name']
    buddy_id = buddy_info['buddy_id']
    
    # Get your stats
    your_xp = get_user_total_xp(userid)
    your_streak = calculate_streak(userid)
    
    # Get buddy's stats  
    buddy_xp = get_user_total_xp(buddy_id)
    buddy_streak = calculate_streak(buddy_id)
    
    # Calculate study time for both (simplified version)
    try:
        session_records = session_sheet.get_all_records() if SHEETS_ENABLED else []
        your_time = sum(int(row.get('Duration', 0)) for row in session_records 
                       if str(row.get('UserID')) == str(userid) and row.get('Status') == 'Completed')
        buddy_time = sum(int(row.get('Duration', 0)) for row in session_records 
                        if str(row.get('UserID')) == str(buddy_id) and row.get('Status') == 'Completed')
        
        your_hours = your_time // 60
        buddy_hours = buddy_time // 60
    except:
        your_hours = 0
        buddy_hours = 0
    
    return (f"👥 Buddy Stats Comparison:\n"
            f"📊 {username}: {your_xp} XP, {your_streak} day streak, {your_hours}h studied\n"
            f"📊 {buddy_name}: {buddy_xp} XP, {buddy_streak} day streak, {buddy_hours}h studied")

# === Study Bot Commands ===
def handle_attend(username, userid):
    if not SHEETS_ENABLED:
        return f"⚠️ {username} , study features are currently unavailable."
    
    now = datetime.now()
    today_date = now.date()

    # Check if this user already gave attendance today
    try:
        records = attendance_sheet.get_all_records()
        for row in records[::-1]:
            if str(row['UserID']) == str(userid):
                try:
                    row_date = datetime.strptime(str(row['Date']), "%Y-%m-%d %H:%M:%S").date()
                    if row_date == today_date:
                        return f"⚠️ {username} , your attendance for today is already recorded! ✅"
                except ValueError:
                    continue
    except:
        pass

    # Log new attendance
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    attendance_sheet.append_row([username, userid, timestamp])
    
    # Update XP
    update_user_xp(username, userid, 10, "Attendance")
    
    streak = calculate_streak(userid)
    return f"✅ {username} ,your attendance is logged and you earned 10 XP! 🔥 Daily Streak: {streak} days."

def handle_start(username, userid):
    if not SHEETS_ENABLED:
        return f"⚠️ {username} , study features are currently unavailable."
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        records = session_sheet.get_all_records()
        # Check if a session is already running
        for row in reversed(records):
            if str(row.get('UserID', '')) == str(userid) and str(row.get('Status', '')).strip() == 'Active':
                return f"⚠️ {username} , you already started a session. Use !stop before starting a new one."
    except Exception as e:
        print(f"Error checking sessions: {e}")

    # Log new session start
    session_sheet.append_row([username, userid, now, "", "", "Active"])
    return f"⏱️ {username} , your study session has started! Use !stop to end it. Happy studying 📚"

def handle_stop(username, userid):
    if not SHEETS_ENABLED:
        return f"⚠️ {username} , study features are currently unavailable."
    
    now = datetime.now()

    try:
        records = session_sheet.get_all_records()
        
        # Find the latest active session
        session_start = None
        row_index = None
        for i in range(len(records) - 1, -1, -1):
            row = records[i]
            if (str(row.get('UserID', '')) == str(userid) and str(row.get('Status', '')).strip() == 'Active'):
                try:
                    session_start = datetime.strptime(row.get('StartTime', ''), "%Y-%m-%d %H:%M:%S")
                    row_index = i + 2
                    break
                except (ValueError, TypeError):
                    print(f"Error parsing start time: {row.get('StartTime', '')}")
                    continue

        if not session_start:
            return f"⚠️ {username} , you didn't start any session. Use !start to begin."

        # Calculate duration and XP
        duration_minutes = int((now - session_start).total_seconds() / 60)
        xp_earned = duration_minutes * 2

        # Update the session record
        session_sheet.update_cell(row_index, 4, now.strftime("%Y-%m-%d %H:%M:%S"))  # EndTime
        session_sheet.update_cell(row_index, 5, duration_minutes)  # Duration
        session_sheet.update_cell(row_index, 6, "Completed")  # Status

        # Update XP
        update_user_xp(username, userid, xp_earned, "Study Session")

        # Badge check
        badges = get_badges(duration_minutes)
        badge_message = f"🎖 {username}, the badge {badges[-1]} has awakened through your silent training. ⚔️" if badges else ""
        
        return f"👩🏻‍💻📓✍🏻 {username} , you studied for {duration_minutes} minutes and earned {xp_earned} XP.{badge_message}"
    
    except Exception as e:
        return f"⚠️ Error stopping session: {str(e)}"

def handle_rank(username, userid):
    if not SHEETS_ENABLED:
        return f"⚠️ {username} ,study features are currently unavailable."
    
    total_xp = get_user_total_xp(userid)
    user_rank = get_rank(total_xp)
    return f"🏅 {username} ,total XP: {total_xp}. You now walk the shadowed path of the {user_rank}. The dojo watches in silence — your spirit grows sharper with every session."

def handle_top():
    if not SHEETS_ENABLED:
        return "⚠️ Study features are currently unavailable."
    
    try:
        records = xp_sheet.get_all_records()
        sorted_users = sorted(records, key=lambda x: int(x.get('TotalXP', 0)), reverse=True)[:5]
        
        message = "🏆 Top 5 Learners: "
        for i, user in enumerate(sorted_users, 1):
            message += f"{i}. {user['Username']} ({user.get('TotalXP', 0)} XP) "

        return message.strip()
    except:
        return "⚠️ Unable to fetch leaderboard data."

def handle_task(username, userid, task_text):
    if not SHEETS_ENABLED:
        return f"⚠️ {username} , study features are currently unavailable."
    
    if not task_text or len(task_text.strip()) < 3:
        return f"⚠️ {username} , please provide a task like: !task Physics Chapter 1"

    try:
        records = task_sheet.get_all_records()
        for row in records[::-1]:
            if str(row.get('UserID', '')) == str(userid) and str(row.get('Status', '')).strip() == 'Pending':
                return f"⚠️ {username} , please complete your previous task first. Use !done to mark it as completed."
    except Exception as e:
        print(f"Error checking tasks: {e}")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    task_name = task_text.strip()
    task_sheet.append_row([username, userid, task_name, now, "", "Pending"])
    return f"✏️ {username} , your task '{task_name}' has been added. Study well! Use !done to complete it."

def handle_done(username, userid):
    if not SHEETS_ENABLED:
        return f"⚠️ {username} , study features are currently unavailable."
    
    try:
        records = task_sheet.get_all_records()

        for i in range(len(records) - 1, -1, -1):
            row = records[i]
            if str(row.get('UserID', '')) == str(userid) and str(row.get('Status', '')).strip() == 'Pending':
                row_index = i + 2
                task_name = row.get('TaskName', '')

                # Mark task as completed
                task_sheet.update_cell(row_index, 5, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                task_sheet.update_cell(row_index, 6, "Completed")

                # Update XP
                xp_earned = 15
                update_user_xp(username, userid, xp_earned, "Task Completed")

                return f"✅ {username} , you completed your task '{task_name}' and earned {xp_earned} XP! Great job! 💪"

        return f"⚠️ {username} , you don't have any active task. Use !task [your task] to add one."
    except Exception as e:
        return f"⚠️ Error completing task: {str(e)}"

def handle_summary(username, userid):
    if not SHEETS_ENABLED:
        return f"⚠️ {username} , study features are currently unavailable."
    
    try:
        # Get total XP
        total_xp = get_user_total_xp(userid)
        
        # Get total study time from sessions
        session_records = session_sheet.get_all_records()
        total_minutes = 0
        for row in session_records:
            if str(row['UserID']) == str(userid) and row['Status'] == 'Completed':
                try:
                    total_minutes += int(row['Duration'])
                except ValueError:
                    pass

        # Get task counts
        task_records = task_sheet.get_all_records()
        completed_tasks = 0
        pending_tasks = 0
        for row in task_records:
            if str(row['UserID']) == str(userid):
                if row['Status'] == 'Completed':
                    completed_tasks += 1
                elif row['Status'] == 'Pending':
                    pending_tasks += 1

        hours = total_minutes // 60
        minutes = total_minutes % 60
        return (f"📊 Today’s Summary for {username} "
                f"⏱️ Total Study Time: {hours}h {minutes}m "
                f"⚜️ XP: {total_xp} "
                f"✅ Completed Task: {completed_tasks} "
                f"🕒 Pending Task: {pending_tasks}")
    except Exception as e:
        return f"⚠️ Error generating summary: {str(e)}"

def handle_goal(username, userid, goal_text):
    if not SHEETS_ENABLED:
        return f"⚠️ {username} , study features are currently unavailable."
    
    if not goal_text or len(goal_text.strip()) < 3:
        return f"⚠️ {username} , please provide a goal like: !goal Complete Math Course"

    try:
        records = goal_sheet.get_all_records()
        # Check if user already has an active goal
        for row in records[::-1]:
            if str(row.get('UserID', '')) == str(userid) and str(row.get('Status', '')).strip() == 'Pending':
                return f"⚠️ {username} , please complete your previous goal first. Use !complete to mark it as completed."
    except Exception as e:
        print(f"Error checking goals: {e}")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    goal_name = goal_text.strip()
    goal_sheet.append_row([username, userid, goal_name, now, "", "Pending"])
    return f"🎯 {username} , your goal '{goal_name}' has been set! Work towards it and use !complete when you achieve it. You'll earn 25 XP! 💪"

def handle_complete(username, userid):
    if not SHEETS_ENABLED:
        return f"⚠️ {username} , study features are currently unavailable."
    
    try:
        records = goal_sheet.get_all_records()

        for i in range(len(records) - 1, -1, -1):
            row = records[i]
            if str(row.get('UserID', '')) == str(userid) and str(row.get('Status', '')).strip() == 'Pending':
                row_index = i + 2
                goal_name = row.get('GoalName', '')

                # Mark goal as completed
                goal_sheet.update_cell(row_index, 5, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                goal_sheet.update_cell(row_index, 6, "Completed")

                # Update XP - Goals give 25 XP
                xp_earned = 25
                update_user_xp(username , userid, xp_earned, "Goal Completed")

                return f"🎉 {username} , congratulations! You completed your goal '{goal_name}' and earned {xp_earned} XP! Amazing achievement! 🏆✨"

        return f"⚠️ {username} , you don't have any active goal. Use !goal [your goal] to set one."
    except Exception as e:
        return f"⚠️ Error completing goal: {str(e)}"
    

def handle_pending(username, userid):
    """Show current pending task for the user"""
    if not SHEETS_ENABLED:
        return f"⚠️ {username} , study features are currently unavailable."
    
    try:
        records = task_sheet.get_all_records()
        
        for row in records[::-1]:  # Check from latest to oldest
            if str(row.get('UserID', '')) == str(userid) and str(row.get('Status', '')).strip() == 'Pending':
                task_name = row.get('TaskName', '')
                created_date = row.get('CreatedDate', '')
                return f"📋 {username} , your pending task: '{task_name}' (Created: {created_date})"
        
        return f"✅ {username} , you don't have any pending tasks. Use !task [task name] to add one."
    
    except Exception as e:
        return f"⚠️ Error fetching pending task: {str(e)}"

def handle_remove(username, userid):
    """Remove current active/pending task"""
    if not SHEETS_ENABLED:
        return f"⚠️ {username} , study features are currently unavailable."
    
    try:
        records = task_sheet.get_all_records()
        
        for i in range(len(records) - 1, -1, -1):  # Check from latest to oldest
            row = records[i]
            if str(row.get('UserID', '')) == str(userid) and str(row.get('Status', '')).strip() == 'Pending':
                row_index = i + 2  # Google Sheets is 1-indexed and has header row
                task_name = row.get('TaskName', '')
                
                # Update status to 'Removed'
                task_sheet.update_cell(row_index, 6, "Removed")
                
                return f"🗑️ {username} , your task '{task_name}' has been removed."
        
        return f"⚠️ {username} , you don't have any pending tasks to remove."
    
    except Exception as e:
        return f"⚠️ Error removing task: {str(e)}"

def handle_comtask(username, userid):
    """Show last 3 completed tasks for the user"""
    if not SHEETS_ENABLED:
        return f"⚠️ {username} , study features are currently unavailable."
    
    try:
        records = task_sheet.get_all_records()
        completed_tasks = []
        
        # Get all completed tasks for this user
        for row in records:
            if str(row.get('UserID', '')) == str(userid) and str(row.get('Status', '')).strip() == 'Completed':
                completed_tasks.append({
                    'name': row.get('TaskName', ''),
                    'completed_date': row.get('CompletedDate', '')
                })
        
        if not completed_tasks:
            return f"📝 {username} , you haven't completed any tasks yet. Keep studying!"
        
        # Get last 3 completed tasks (reverse to get most recent first)
        recent_tasks = completed_tasks[-3:][::-1]
        
        message = f"📚 {username} 's last {len(recent_tasks)} completed task(s): "
        for i, task in enumerate(recent_tasks, 1):
            message += f"{i}. {task['name']} "
        
        return message.strip()
    
    except Exception as e:
        return f"⚠️ Error fetching completed tasks: {str(e)}"

def parse_pomodoro_time(text):
    """Parse time from text, return minutes"""
    text = text.lower().strip()
    
    # If just a number, assume minutes
    if text.isdigit():
        return int(text)
    
    # Pattern for numbers followed by time units
    patterns = [
        (r'(\d+)\s*(?:min|minute|minutes|m)', 1),     # minutes
        (r'(\d+)\s*(?:h|hr|hour|hours)', 60),        # hours
        (r'(\d+)\s*(?:sec|second|seconds|s)', 1/60), # seconds
    ]
    
    for pattern, multiplier in patterns:
        match = re.search(pattern, text)
        if match:
            number = int(match.group(1))
            return int(number * multiplier)
    
    return None

def pomodoro_worker(username, userid, session_duration, total_sessions, break_duration):
    """Background worker for pomodoro timer"""
    global active_pomodoros
    
    try:
        for session_num in range(1, total_sessions + 1):
            if userid not in active_pomodoros:
                # User cancelled the pomodoro
                return
            
            # Update current session info
            active_pomodoros[userid]['current_session'] = session_num
            active_pomodoros[userid]['status'] = 'studying'
            
            # Study session
            send_message(VIDEO_ID, f"🍅 {username}, Pomodoro session {session_num}/{total_sessions} started! Focus time: {session_duration} minutes", ACCESS_TOKEN)
            
            # Wait for session duration
            time.sleep(session_duration * 60)
            
            # Check if pomodoro is still active
            if userid not in active_pomodoros:
                return
            
            # Session completed
            send_message(VIDEO_ID, f"✅ {username}, session {session_num} completed! Great work! 👏", ACCESS_TOKEN)
            
            # Award XP for completed session
            update_user_xp(username, userid, session_duration * 2, "Pomodoro Session")
            
            # If not the last session, start break
            if session_num < total_sessions:
                active_pomodoros[userid]['status'] = 'break'
                send_message(VIDEO_ID, f"☕ {username}, time for a {break_duration}-minute break! Relax and recharge 😌", ACCESS_TOKEN)
                
                # Wait for break duration
                time.sleep(break_duration * 60)
                
                # Check if pomodoro is still active
                if userid not in active_pomodoros:
                    return
                
                # Break completed
                send_message(VIDEO_ID, f"⏰ {username}, break time is over! Ready for session {session_num + 1}? 💪", ACCESS_TOKEN)
        
        # All sessions completed
        total_study_time = session_duration * total_sessions
        bonus_xp = 20 if total_sessions >= 4 else 10
        update_user_xp(username, userid, bonus_xp, "Pomodoro Completion Bonus")
        
        send_message(VIDEO_ID, f"🎉 {username}, congratulations! You completed all {total_sessions} Pomodoro sessions! Total study time: {total_study_time} minutes. Bonus: +{bonus_xp} XP! 🏆", ACCESS_TOKEN)
        
        # Remove from active pomodoros
        if userid in active_pomodoros:
            del active_pomodoros[userid]
            
    except Exception as e:
        print(f"❌ Error in pomodoro worker: {e}")
        # Clean up on error
        if userid in active_pomodoros:
            del active_pomodoros[userid]

def handle_pomo(username, userid, pomo_text):
    """Handle pomodoro timer commands"""
    global active_pomodoros, pomodoro_threads
    
    if not pomo_text or len(pomo_text.strip()) < 1:
        return f"⚠️ {username}, use: !pomo 25 4 5 (25min sessions, 4 total, 5min breaks) or !pomo status or !pomo stop"
    
    text = pomo_text.strip()
    
    # Handle status command
    if text.lower() == "status":
        if userid in active_pomodoros:
            pomo = active_pomodoros[userid]
            status_emoji = "📚" if pomo['status'] == 'studying' else "☕"
            return f"{status_emoji} {username}, Pomodoro active: Session {pomo['current_session']}/{pomo['total_sessions']} - Status: {pomo['status'].title()}"
        else:
            return f"⚠️ {username}, you don't have an active Pomodoro timer."
    
    # Handle stop command
    if text.lower() == "stop":
        if userid in active_pomodoros:
            del active_pomodoros[userid]
            return f"🛑 {username}, your Pomodoro timer has been stopped."
        else:
            return f"⚠️ {username}, you don't have an active Pomodoro timer to stop."
    
    # Check if user already has active pomodoro
    if userid in active_pomodoros:
        return f"⚠️ {username}, you already have an active Pomodoro! Use !pomo stop to cancel it first."
    
    # Parse parameters: session_duration total_sessions break_duration
    params = text.split()
    
    if len(params) != 3:
        return f"⚠️ {username}, format: !pomo <session_minutes> <total_sessions> <break_minutes>. Example: !pomo 25 4 5"
    
    try:
        session_duration = parse_pomodoro_time(params[0])
        total_sessions = int(params[1])
        break_duration = parse_pomodoro_time(params[2])
        
        if not session_duration or not break_duration:
            return f"⚠️ {username}, I couldn't parse the time values. Use numbers like: !pomo 25 4 5"
        
        # Validation
        if session_duration < 5 or session_duration > 120:
            return f"⚠️ {username}, session duration must be between 5-120 minutes."
        
        if total_sessions < 1 or total_sessions > 12:
            return f"⚠️ {username}, total sessions must be between 1-12."
        
        if break_duration < 1 or break_duration > 60:
            return f"⚠️ {username}, break duration must be between 1-60 minutes."
        
    except ValueError:
        return f"⚠️ {username}, invalid format. Use: !pomo 25 4 5 (numbers only for sessions)"
    
    # Store pomodoro info
    active_pomodoros[userid] = {
        'username': username,
        'session_duration': session_duration,
        'total_sessions': total_sessions,
        'break_duration': break_duration,
        'current_session': 0,
        'status': 'preparing',
        'start_time': datetime.now()
    }
    
    # Start pomodoro thread
    pomo_thread = threading.Thread(
        target=pomodoro_worker,
        args=(username, userid, session_duration, total_sessions, break_duration),
        daemon=True
    )
    pomo_thread.start()
    pomodoro_threads.append(pomo_thread)
    
    total_time = (session_duration * total_sessions) + (break_duration * (total_sessions - 1))
    return f"🍅 {username}, Pomodoro timer started! {total_sessions} sessions of {session_duration}min with {break_duration}min breaks. Total time: ~{total_time}min. Use !pomo status or !pomo stop"


def process_command(message, author_name, author_id):
    """Process study bot commands from chat messages"""
    message_lower = message.lower().strip()
    
    # Command mapping
    if message_lower == "!attend":
        return handle_attend(author_name, author_id)
    elif message_lower == "!start":
        return handle_start(author_name, author_id)
    elif message_lower == "!stop":
        return handle_stop(author_name, author_id)
    elif message_lower == "!rank":
        return handle_rank(author_name, author_id)
    elif message_lower == "!top":
        return handle_top()
    elif message_lower == "!done":
        return handle_done(author_name, author_id)
    elif message_lower == "!summary":
        return handle_summary(author_name, author_id)
    elif message_lower == "!complete":
        return handle_complete(author_name, author_id)
    elif message_lower.startswith("!task "):
        task_text = message[6:]
        return handle_task(author_name, author_id, task_text)
    elif message_lower.startswith("!goal "):
        goal_text = message[6:]
        return handle_goal(author_name, author_id, goal_text)
    elif message_lower == "!pending":
        return handle_pending(author_name, author_id)
    elif message_lower == "!remove":
        return handle_remove(author_name, author_id)
    elif message_lower == "!comtask":
        return handle_comtask(author_name, author_id)
    elif message_lower.startswith("!remind "):
        remind_text = message[8:]
        return handle_remind(author_name, author_id, remind_text)
    elif message_lower == "!buddy" or message_lower.startswith("!buddy "):
        buddy_command = message[7:] if len(message) > 7 else ""
        return handle_buddy(author_name, author_id, buddy_command)
    elif message_lower == "!pomo" or message_lower.startswith("!pomo "):
        pomo_command = message[6:] if len(message) > 6 else ""
        return handle_pomo(author_name, author_id, pomo_command)
    elif message_lower == "!help":
        return ("Commands: !attend !start !stop | !rank !top | !task !done !remove !comtask | !goal !complete | !summary !pending | !ask <your question> (Stuck on something? Sunnie Study GPT is here to help—ask away)")
    
    return None

def run_bot():
    if not VIDEO_ID:
        print("❌ Error: YOUTUBE_VIDEO_ID environment variable not set.")
        return

    # 🔁 Refresh access token before anything else
    refresh_access_token_auto()

    # ✅ Start timer system
    start_timer_system()

    chat = pytchat.create(video_id=VIDEO_ID)
    print("✅ Bot started...")

    while chat.is_alive():
        for c in chat.get().sync_items():
            print(f"{c.author.name}: {c.message}")
            
            # Increment chat count for timer system
            increment_chat_count()
            
            # Handle original !hello command
            if "!hello" in c.message.lower():
                reply = f"Hi {c.author.name} !"
                send_message(VIDEO_ID, reply, ACCESS_TOKEN)
            
            # Handle study bot commands
            response = process_command(c.message, c.author.name, c.author.channelId)
            if response:
                send_message(VIDEO_ID, response, ACCESS_TOKEN)
                
        time.sleep(1)

@app.route("/")
def home():
    status = "✅ Connected" if SHEETS_ENABLED else "❌ Disconnected"
    return f"🤖 YouTube Study Bot is running! Google Sheets: {status}"

@app.route("/ping")
def ping():
    return "🟢 YouTube Study Bot is alive!"

def start_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ✅ Start Flask in a thread, run bot in main thread
if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    run_bot()  # 🔥 must be in main thread

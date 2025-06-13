import os
import time
import threading
import requests
import pytchat
from flask import Flask
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

app = Flask(__name__)

# YouTube API credentials
ACCESS_TOKEN = os.getenv("YOUTUBE_ACCESS_TOKEN")
REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")
CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
VIDEO_ID = os.getenv("YOUTUBE_VIDEO_ID")

# === Google Sheet Setup ===
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "/etc/secrets/credentials.json")
scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]

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

def send_message(video_id, message_text, access_token):
    url = "https://youtube.googleapis.com/youtube/v3/liveChat/messages?part=snippet"

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
    if xp >= 500:
        return "📘 Scholar"
    elif xp >= 300:
        return "📗 Master"
    elif xp >= 150:
        return "📙 Intermediate"
    elif xp >= 50:
        return "📕 Beginner"
    else:
        return "🍼 Newbie"

def get_badges(total_minutes):
    badges = []
    if total_minutes >= 50:
        badges.append("🥉 Bronze Mind")
    if total_minutes >= 110:
        badges.append("🥈 Silver Brain")
    if total_minutes >= 150:
        badges.append("🥇 Golden Genius")
    if total_minutes >= 240:
        badges.append("🔷 Diamond Crown")
    return badges

# === Study Bot Commands ===
def handle_attend(username, userid):
    if not SHEETS_ENABLED:
        return f"⚠️ {username}, study features are currently unavailable."
    
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
                        return f"⚠️ {username}, your attendance for today is already recorded! ✅"
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
    return f"✅ {username}, your attendance is logged and you earned 10 XP! 🔥 Daily Streak: {streak} days."

def handle_start(username, userid):
    if not SHEETS_ENABLED:
        return f"⚠️ {username}, study features are currently unavailable."
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        records = session_sheet.get_all_records()
        # Check if a session is already running
        for row in reversed(records):
            if str(row.get('UserID', '')) == str(userid) and str(row.get('Status', '')).strip() == 'Active':
                return f"⚠️ {username}, you already started a session. Use !stop before starting a new one."
    except Exception as e:
        print(f"Error checking sessions: {e}")

    # Log new session start
    session_sheet.append_row([username, userid, now, "", "", "Active"])
    return f"⏱️ {username}, your study session has started! Use !stop to end it. Happy studying 📚"

def handle_stop(username, userid):
    if not SHEETS_ENABLED:
        return f"⚠️ {username}, study features are currently unavailable."
    
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
            return f"⚠️ {username}, you didn't start any session. Use !start to begin."

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
        badge_message = f" 🎖 {username}, you unlocked a badge: {badges[-1]}! Keep it up!" if badges else ""

        return f"👩🏻‍💻📓✍🏻 {username}, you studied for {duration_minutes} minutes and earned {xp_earned} XP.{badge_message}"
    
    except Exception as e:
        return f"⚠️ Error stopping session: {str(e)}"

def handle_rank(username, userid):
    if not SHEETS_ENABLED:
        return f"⚠️ {username}, study features are currently unavailable."
    
    total_xp = get_user_total_xp(userid)
    user_rank = get_rank(total_xp)
    return f"🏅 {username}, you have {total_xp} XP. Your rank is: {user_rank}"

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
        return f"⚠️ {username}, study features are currently unavailable."
    
    if not task_text or len(task_text.strip()) < 3:
        return f"⚠️ {username}, please provide a task like: !task Physics Chapter 1"

    try:
        records = task_sheet.get_all_records()
        for row in records[::-1]:
            if str(row.get('UserID', '')) == str(userid) and str(row.get('Status', '')).strip() == 'Pending':
                return f"⚠️ {username}, please complete your previous task first. Use !done to mark it as completed."
    except Exception as e:
        print(f"Error checking tasks: {e}")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    task_name = task_text.strip()
    task_sheet.append_row([username, userid, task_name, now, "", "Pending"])
    return f"✏️ {username}, your task '{task_name}' has been added. Study well! Use !done to complete it."

def handle_done(username, userid):
    if not SHEETS_ENABLED:
        return f"⚠️ {username}, study features are currently unavailable."
    
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

                return f"✅ {username}, you completed your task '{task_name}' and earned {xp_earned} XP! Great job! 💪"

        return f"⚠️ {username}, you don't have any active task. Use !task [your task] to add one."
    except Exception as e:
        return f"⚠️ Error completing task: {str(e)}"

def handle_summary(username, userid):
    if not SHEETS_ENABLED:
        return f"⚠️ {username}, study features are currently unavailable."
    
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
        return (f"📊 {username}'s Summary: "
                f"⏱️ Study Time: {hours}h {minutes}m "
                f"⚜️ XP: {total_xp} "
                f"✅ Completed: {completed_tasks} "
                f"🕒 Pending: {pending_tasks}")
    except Exception as e:
        return f"⚠️ Error generating summary: {str(e)}"

def handle_goal(username, userid, goal_text):
    if not SHEETS_ENABLED:
        return f"⚠️ {username}, study features are currently unavailable."
    
    if not goal_text or len(goal_text.strip()) < 3:
        return f"⚠️ {username}, please provide a goal like: !goal Complete Math Course"

    try:
        records = goal_sheet.get_all_records()
        # Check if user already has an active goal
        for row in records[::-1]:
            if str(row.get('UserID', '')) == str(userid) and str(row.get('Status', '')).strip() == 'Pending':
                return f"⚠️ {username}, please complete your previous goal first. Use !complete to mark it as completed."
    except Exception as e:
        print(f"Error checking goals: {e}")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    goal_name = goal_text.strip()
    goal_sheet.append_row([username, userid, goal_name, now, "", "Pending"])
    return f"🎯 {username}, your goal '{goal_name}' has been set! Work towards it and use !complete when you achieve it. You'll earn 25 XP! 💪"

def handle_complete(username, userid):
    if not SHEETS_ENABLED:
        return f"⚠️ {username}, study features are currently unavailable."
    
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
                update_user_xp(username, userid, xp_earned, "Goal Completed")

                return f"🎉 {username}, congratulations! You completed your goal '{goal_name}' and earned {xp_earned} XP! Amazing achievement! 🏆✨"

        return f"⚠️ {username}, you don't have any active goal. Use !goal [your goal] to set one."
    except Exception as e:
        return f"⚠️ Error completing goal: {str(e)}"

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
        task_text = message[6:]  # Remove "!task " prefix
        return handle_task(author_name, author_id, task_text)
    elif message_lower.startswith("!goal "):
        goal_text = message[6:]  # Remove "!goal " prefix
        return handle_goal(author_name, author_id, goal_text)
    elif message_lower == "!help":
        return ("Commands: !attend !start !stop | !rank !top | !task !done !remove !comtask | !goal !complete | !summary !pending | !ai (ask anything)")
    
    return None

def run_bot():
    if not VIDEO_ID:
        print("❌ Error: YOUTUBE_VIDEO_ID environment variable not set.")
        return

    # Start timer system
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
                reply = f"Hi {c.author.name}!"
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

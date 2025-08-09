import os
import time
import json
import threading
import requests
import html
from dotenv import load_dotenv
from apprise import Apprise
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)

# === Load Config ===
load_dotenv()
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "60"))

WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "watchlists.json")

# === Globals ===
live_status = {}  # {twitch_user_id: bool}
user_ids_cache = {}  # {username: user_id}
watchlists = {}

# === Conversation states ===
SET_APPRISE_CONFIRM = 1

# === Utility: Timestamped logging ===
def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

# === File Utilities ===
def load_watchlists():
    if not os.path.exists(WATCHLIST_FILE):
        return {}
    with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_watchlists(watchlists_data):
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(watchlists_data, f, indent=2)

watchlists = load_watchlists()

# === Twitch API Utilities ===
def get_app_token():
    log("Requesting Twitch app token...")
    resp = requests.post("https://id.twitch.tv/oauth2/token", params={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials"
    })
    resp.raise_for_status()
    log("Twitch token received.")
    return resp.json()["access_token"]

def get_user_ids(headers, usernames):
    usernames = [u.lower() for u in usernames]
    to_fetch = [u for u in usernames if u not in user_ids_cache]
    if to_fetch:
        log(f"Fetching Twitch user IDs for: {', '.join(to_fetch)}")
        resp = requests.get("https://api.twitch.tv/helix/users",
                            headers=headers,
                            params=[('login', name) for name in to_fetch])
        resp.raise_for_status()
        for user in resp.json()["data"]:
            user_ids_cache[user['login']] = user['id']
            log(f"Resolved {user['login']} => {user['id']}")
    return {u: user_ids_cache.get(u) for u in usernames if u in user_ids_cache}

def get_live_streams(headers, user_ids):
    if not user_ids:
        return {}
    resp = requests.get("https://api.twitch.tv/helix/streams",
                        headers=headers,
                        params=[('user_id', uid) for uid in user_ids])
    resp.raise_for_status()
    return {stream['user_id']: stream for stream in resp.json()["data"]}

# === Notification Utility ===
def send_notification(chat_id, title, body):
    ap = Apprise()
    # Always send to Telegram
    ap.add(f"tgram://{BOT_TOKEN}/{chat_id}")
    # Add extra user URLs if available
    extra_urls = watchlists.get(chat_id, {}).get("apprise_urls", [])
    for url in extra_urls:
        ap.add(url)
    ap.notify(title=title, body=body)

# === Background Twitch Monitor ===
def monitor_twitch():
    log("Twitch monitor thread started.")
    token = get_app_token()
    headers = {
        "Client-ID": CLIENT_ID,
        "Authorization": f"Bearer {token}"
    }

    global live_status
    while True:
        try:
            log("Polling Twitch for stream updates...")
            # Gather all channels across all users
            all_channels = set()
            for data in watchlists.values():
                all_channels.update(data.get("channels", []))

            # Resolve to user IDs
            user_id_map = get_user_ids(headers, list(all_channels))

            # Poll live streams
            live_data = get_live_streams(headers, user_id_map.values())
            current_live = {uid: True for uid in live_data}

            # Check changes per user
            for chat_id, data in watchlists.items():
                for username in data.get("channels", []):
                    uid = user_id_map.get(username.lower())
                    if not uid:
                        continue

                    was_live = live_status.get(uid, False)
                    is_live = current_live.get(uid, False)

                    if is_live and not was_live:
                        s = live_data[uid]
                        title = f"🔴 {username} is now LIVE!"
                        body = f"{s['title']}\nGame: {s['game_name']}\nViewers: {s['viewer_count']}\nhttps://twitch.tv/{username}"
                        send_notification(chat_id, title, body)
                        log(f"Notified {chat_id} — {username} went LIVE.")

                    elif not is_live and was_live:
                        title = f"⚫ {username} has gone offline."
                        body = f"{username} is no longer streaming.\nhttps://twitch.tv/{username}"
                        send_notification(chat_id, title, body)
                        log(f"Notified {chat_id} — {username} went OFFLINE.")

            live_status = current_live
        except Exception as e:
            log(f"[ERROR] Twitch monitor: {e}")

        time.sleep(CHECK_INTERVAL)

# === Telegram Bot Commands ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    username = update.effective_user.username or update.effective_user.full_name
    if chat_id not in watchlists:
        watchlists[chat_id] = {"channels": [], "apprise_urls": []}
        save_watchlists(watchlists)
    log(f"User {username} ({chat_id}) started the bot.")
    await update.message.reply_text(
        "👋 Welcome to the Twitchrise bot for Telegram!\n\n" 
        "Use /add <channel> to watch a Twitch streamer.\n"
        "Use /remove <channel> to stop watching.\n"
        "Use /list to see your watchlist.\n"
        "Use /setapprise <url> to add extra notification targets.\n"
        "Use /rmapprise <number> to remove already added notification targets.\n"
        "Use /listapprise to list all added notification targets.\n\n"
        "You can see the supported URLs and their formats here - https://github.com/caronc/apprise#supported-notifications. \n\n"
        "Please remember that these will work in addition to Telegram, you will alwyas receive updates in this chat irrespective of if you add more targets or not."
    )

async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    username = update.effective_user.username or update.effective_user.full_name
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /add <channel_name>")
        return

    channel = context.args[0].lower()
    watchlists.setdefault(chat_id, {"channels": [], "apprise_urls": []})

    if channel not in watchlists[chat_id]["channels"]:
        watchlists[chat_id]["channels"].append(channel)
        save_watchlists(watchlists)
        log(f"User {username} ({chat_id}) added channel: {channel}")
        await update.message.reply_text(f"✅ Added {channel} to your watchlist.")

        # === Check if channel is live immediately ===
        try:
            token = get_app_token()
            headers = {
                "Client-ID": CLIENT_ID,
                "Authorization": f"Bearer {token}"
            }
            user_id_map = get_user_ids(headers, [channel])
            uid = user_id_map.get(channel)
            if uid:
                live_data = get_live_streams(headers, [uid])
                if uid in live_data:
                    s = live_data[uid]
                    title = f"🟢 {channel} is already LIVE!"
                    body = f"{s['title']}\nGame: {s['game_name']}\nViewers: {s['viewer_count']}\nhttps://twitch.tv/{channel}"
                    send_notification(chat_id, title, body)
                    log(f"Immediate notification to {username} ({chat_id}) — {channel} already LIVE.")
                    live_status[uid] = True
        except Exception as e:
            log(f"[ERROR] Live check on add failed: {e}")

    else:
        await update.message.reply_text(f"⚠️ {channel} is already in your watchlist.")

async def remove_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    username = update.effective_user.username or update.effective_user.full_name
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /remove <channel_name>")
        return
    channel = context.args[0].lower()
    if chat_id in watchlists and channel in watchlists[chat_id]["channels"]:
        watchlists[chat_id]["channels"].remove(channel)
        save_watchlists(watchlists)
        log(f"User {username} ({chat_id}) removed channel: {channel}")
        await update.message.reply_text(f"🗑 Removed {channel} from your watchlist.")
    else:
        await update.message.reply_text(f"⚠️ {channel} is not in your watchlist.")

async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    username = update.effective_user.username or update.effective_user.full_name
    channels = watchlists.get(chat_id, {}).get("channels", [])
    log(f"User {username} ({chat_id}) requested watchlist: {channels}")

    if channels:
        message = "📜 Your watchlist: (tap to copy)\n"
        for ch in channels:
            safe_ch = html.escape(ch)
            message += f"• <code>{safe_ch}</code>\n"
        await update.message.reply_text(message, parse_mode="HTML")
    else:
        await update.message.reply_text("📭 Your watchlist is empty.")

# === /setapprise flow ===
async def set_apprise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /setapprise <apprise_url>")
        return ConversationHandler.END

    url = context.args[0]
    context.user_data["pending_apprise_url"] = url

    # Test the URL
    ap = Apprise()
    ap.add(url)
    worked = ap.notify(title="Test Notification", body="If you see this, the Apprise URL works!")

    if worked:
        await update.message.reply_text(
            "✅ Test notification sent successfully.\n"
            "Do you want to save this URL for future alerts? Please reply 'yes' or 'no'"
        )
        return SET_APPRISE_CONFIRM
    else:
        await update.message.reply_text("❌ The Apprise URL did not work. Please check and try again.")
        return ConversationHandler.END

async def confirm_apprise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    reply = update.message.text.strip().lower()
    if reply in ("yes", "y"):
        url = context.user_data.get("pending_apprise_url")
        if not url:
            await update.message.reply_text("⚠️ No pending URL found.")
            return ConversationHandler.END

        watchlists.setdefault(chat_id, {"channels": [], "apprise_urls": []})
        if url not in watchlists[chat_id]["apprise_urls"]:
            watchlists[chat_id]["apprise_urls"].append(url)
            save_watchlists(watchlists)
            log(f"User {chat_id} saved Apprise URL: {url}")
            await update.message.reply_text("💾 Saved your Apprise URL.")
    else:
        await update.message.reply_text("❌ Not saved.")

    return ConversationHandler.END

async def cancel_set_apprise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

async def list_apprise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    apprise_urls = watchlists.get(chat_id, {}).get("apprise_urls", [])
    if not apprise_urls:
        await update.message.reply_text("📭 You have no saved Apprise URLs.")
        return

    message = "🔗 Your saved Apprise URLs: (tap to copy)\n"
    for i, url in enumerate(apprise_urls, start=1):
        safe_url = html.escape(url)  # escape &, <, >
        message += f"({i}) <code>{safe_url}</code>\n"

    await update.message.reply_text(message, parse_mode="HTML")

async def remove_apprise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    apprise_urls = watchlists.get(chat_id, {}).get("apprise_urls", [])

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /rmapprise <number>")
        return

    try:
        index = int(context.args[0])
        if index < 1 or index > len(apprise_urls):
            await update.message.reply_text("⚠️ Invalid number. Use /listapprise to see saved URLs.")
            return
    except ValueError:
        await update.message.reply_text("⚠️ Please provide a valid number.")
        return

    removed_url = apprise_urls.pop(index - 1)
    watchlists[chat_id]["apprise_urls"] = apprise_urls
    save_watchlists(watchlists)
    log(f"User {chat_id} removed Apprise URL: {removed_url}")
    await update.message.reply_text(f"🗑 Removed Apprise URL:\n{removed_url}")

# === Main Entry ===
if __name__ == "__main__":
    # Start Twitch monitoring in background
    t = threading.Thread(target=monitor_twitch, daemon=True)
    t.start()

    # Start Telegram bot
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_channel))
    app.add_handler(CommandHandler("remove", remove_channel))
    app.add_handler(CommandHandler("list", list_channels))
    app.add_handler(CommandHandler("listapprise", list_apprise))
    app.add_handler(CommandHandler("rmapprise", remove_apprise))
    
    # Conversation for /setapprise
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("setapprise", set_apprise)],
        states={
            SET_APPRISE_CONFIRM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_apprise)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_set_apprise)]
    )
    app.add_handler(conv_handler)

    log("Telegram bot is running...")
    app.run_polling()

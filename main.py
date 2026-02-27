import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
import requests
import json
import asyncio
from datetime import datetime, timedelta
import time
import os

from config import *

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================
# 📦 USER DATABASE MANAGEMENT
# ============================================
class UserDatabase:
    def __init__(self, db_file):
        self.db_file = db_file
        self.users = self.load_users()
    
    def load_users(self):
        """Load users from JSON file"""
        try:
            if os.path.exists(self.db_file):
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Error loading database: {e}")
            return {}
    
    def save_users(self):
        """Save users to JSON file"""
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.users, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving database: {e}")
    
    def is_verified(self, user_id):
        """Check if user is verified"""
        user_id = str(user_id)
        if user_id not in self.users:
            return False
        
        user_data = self.users[user_id]
        last_check = datetime.fromisoformat(user_data.get('last_check', '2000-01-01'))
        
        # Check if verification needs refresh
        if datetime.now() - last_check > timedelta(seconds=CHECK_INTERVAL):
            return False
        
        return user_data.get('verified', False)
    
    def set_verified(self, user_id, verified=True):
        """Set user verification status"""
        user_id = str(user_id)
        self.users[user_id] = {
            'verified': verified,
            'last_check': datetime.now().isoformat(),
            'joined_at': self.users.get(user_id, {}).get('joined_at', datetime.now().isoformat())
        }
        self.save_users()
    
    def get_user_stats(self):
        """Get user statistics"""
        total_users = len(self.users)
        verified_users = sum(1 for u in self.users.values() if u.get('verified', False))
        return total_users, verified_users
    
    def remove_user(self, user_id):
        """Remove user from database"""
        user_id = str(user_id)
        if user_id in self.users:
            del self.users[user_id]
            self.save_users()
            return True
        return False

# Initialize database
db = UserDatabase(DATABASE_FILE)

# ============================================
# ✅ VERIFICATION FUNCTIONS
# ============================================
async def check_membership(user_id, context):
    """Check if user is member of all required channels"""
    try:
        for channel in REQUIRED_CHANNELS:
            try:
                member = await context.bot.get_chat_member(
                    chat_id=f"@{channel['username']}", 
                    user_id=user_id
                )
                if member.status in ['left', 'kicked']:
                    return False
            except Exception as e:
                logger.error(f"Error checking channel {channel['username']}: {e}")
                # If bot can't check channel, consider it as not verified
                return False
        return True
    except Exception as e:
        logger.error(f"Membership check error: {e}")
        return False

async def verify_user(update: Update, context: ContextTypes.DEFAULT_TYPE, show_message=True):
    """Verify user and show message if needed"""
    user_id = update.effective_user.id
    
    if await check_membership(user_id, context):
        db.set_verified(user_id, True)
        return True
    else:
        db.set_verified(user_id, False)
        
        if show_message:
            await show_verify_required(update, context)
        return False

async def show_verify_required(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show verification required message"""
    keyboard = []
    
    # Add channel buttons
    for channel in REQUIRED_CHANNELS:
        keyboard.append([
            InlineKeyboardButton(f"📢 Join {channel['name']}", url=channel['url'])
        ])
    
    # Add verify button
    keyboard.append([
        InlineKeyboardButton("✅ I've Joined - Verify", callback_data="verify_now")
    ])
    
    # Add help button
    keyboard.append([
        InlineKeyboardButton("❓ Help", callback_data="help")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = """🔒 **VERIFICATION REQUIRED**

To use this bot, you must join both channels below:

📌 After joining both channels, click **"I've Joined - Verify"** button.

⚡ **Powered by:** @developer_apon
"""
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            message, 
            reply_markup=reply_markup, 
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            message, 
            reply_markup=reply_markup, 
            parse_mode=ParseMode.MARKDOWN
        )

# ============================================
# 🌐 API FUNCTIONS
# ============================================
async def fetch_player_data(uid):
    """Fetch player data from API using UID"""
    try:
        # Prepare API parameters
        params = {}
        for key, value in API_PARAMS.items():
            if value is None:
                params[key] = uid
            else:
                params[key] = value
        
        # Build URL
        url = f"{API_BASE_URL}{API_ENDPOINT}"
        
        # Headers to avoid blocking
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        logger.info(f"Fetching data from API for UID: {uid}")
        
        # Make request with timeout
        response = requests.get(
            url, 
            params=params, 
            headers=headers, 
            timeout=15,
            verify=True
        )
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"API Response received for UID: {uid}")
            
            # Check API response based on mapping
            success_key = API_MAPPING.get("success_key", "success")
            
            # Handle different response structures
            if isinstance(data, dict):
                if data.get(success_key, False):
                    # Get data using data_key from mapping
                    data_key = API_MAPPING.get("data_key", "data")
                    player_data = data.get(data_key, {})
                    
                    # If player_data is empty, try to use the whole data
                    if not player_data:
                        player_data = data
                    
                    return {
                        "success": True, 
                        "data": player_data,
                        "raw": data
                    }
                else:
                    error_msg = data.get(
                        API_MAPPING.get("error_key", "error"), 
                        "Unknown error from API"
                    )
                    return {"success": False, "error": error_msg}
            else:
                return {"success": False, "error": "Invalid API response format"}
        else:
            return {
                "success": False, 
                "error": f"API Error: {response.status_code}"
            }
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout for UID: {uid}")
        return {"success": False, "error": "Timeout - Server is slow"}
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error for UID: {uid}")
        return {"success": False, "error": "Connection error - API might be down"}
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error for UID {uid}: {e}")
        return {"success": False, "error": f"Request failed: {str(e)[:50]}"}
    except Exception as e:
        logger.error(f"Unexpected error for UID {uid}: {e}")
        return {"success": False, "error": f"Unexpected error: {str(e)[:50]}"}

def format_profile(api_result, uid):
    """Format API data into nice profile message"""
    try:
        if not api_result.get("success"):
            return None
        
        data = api_result.get("data", {})
        
        # Extract player data based on mapping
        player_map = API_MAPPING.get("player", {})
        
        # Helper function to get nested values
        def get_value(key):
            if not key:
                return "N/A"
            
            # Handle nested keys with dot notation (e.g., "player.name")
            if "." in key:
                parts = key.split(".")
                value = data
                for part in parts:
                    if isinstance(value, dict):
                        value = value.get(part, "N/A")
                    else:
                        return "N/A"
                return value if value not in [None, "", "N/A"] else "N/A"
            
            # Simple key
            value = data.get(key, "N/A")
            return value if value not in [None, "", "N/A"] else "N/A"
        
        # Get all values
        nickname = get_value(player_map.get("nickname", "nickname"))
        level = get_value(player_map.get("level", "level"))
        likes = get_value(player_map.get("likes", "likes"))
        region = get_value(player_map.get("region", "region"))
        guild = get_value(player_map.get("guild", "guild"))
        br_rank = get_value(player_map.get("br_rank", "br_rank"))
        cs_rank = get_value(player_map.get("cs_rank", "cs_rank"))
        badges = get_value(player_map.get("badges", "badges"))
        honor = get_value(player_map.get("honor_score", "honor_score"))
        
        # Format the profile
        profile = f"""🎮 **FREE FIRE PLAYER INFO**

━━━━━━━━━━━━━━━━━━━━━
👤 **PLAYER DETAILS**
━━━━━━━━━━━━━━━━━━━━━
✨ **Name:** {nickname}
🆔 **UID:** {uid}
📊 **Level:** {level}
❤️ **Likes:** {likes}
🌍 **Region:** {region}
🏰 **Guild:** {guild}
🎖️ **Badges:** {badges}
🛡️ **Honor Score:** {honor}

━━━━━━━━━━━━━━━━━━━━━
🏆 **RANKINGS**
━━━━━━━━━━━━━━━━━━━━━
🥇 **BR Rank:** {br_rank}
🥈 **CS Rank:** {cs_rank}

━━━━━━━━━━━━━━━━━━━━━
⏰ **Last Update:** {datetime.now().strftime('%d %b %Y, %I:%M %p')}

━━━━━━━━━━━━━━━━━━━━━
👑 **Developer:** @{OWNER_USERNAME}
⚡ **Powered by:** Apon Developers Hub 💻
"""
        return profile
        
    except Exception as e:
        logger.error(f"Format error: {e}")
        return None

# ============================================
# 🤖 BOT COMMAND HANDLERS
# ============================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    
    # Check verification without showing message
    if await verify_user(update, context, show_message=False):
        welcome = f"""👋 **Welcome {user.first_name}!**

I'm a **Free Fire Info Bot** that can fetch any player's profile information using their UID.

📌 **How to use:**
Just send me any **Free Fire UID** (example: `1484443876`)

🔍 I'll fetch and show you complete profile info!

📢 **Commands:**
/start - Show this message
/help - Get help & info
/about - About this bot
/stats - Bot statistics (admin only)

⚡ **Powered by:** @developer_apon
"""
        await update.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN)
    else:
        # verify_user will show verification message automatically
        pass

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = """❓ **HELP & SUPPORT**

**How to use this bot:**
1️⃣ Join both required channels
2️⃣ Send any Free Fire UID
3️⃣ Get instant profile info

**What info you get:**
✅ Player name & level
✅ UID & region
✅ Likes & badges
✅ Guild info
✅ BR & CS ranks
✅ Honor score

**Example UID:** `1484443876`

**Need support?**
👤 Contact: @developer_apon
📢 Channel: @developer_apon_07

⚡ **Powered by:** Apon Developers Hub
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """About command handler"""
    total_users, verified_users = db.get_user_stats()
    
    about_text = f"""ℹ️ **ABOUT THIS BOT**

🤖 **Bot Name:** Free Fire Info Bot
👨‍💻 **Developer:** @{OWNER_USERNAME}
📊 **Version:** 2.0
📅 **Created:** 2026

**Statistics:**
👥 Total Users: {total_users}
✅ Verified Users: {verified_users}
📡 API Status: Active

**Required Channels:**
"""
    for channel in REQUIRED_CHANNELS:
        about_text += f"📢 {channel['name']}\n"
    
    about_text += f"""
⚡ **Powered by:** Apon Developers Hub
"""
    await update.message.reply_text(about_text, parse_mode=ParseMode.MARKDOWN)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stats command (admin only)"""
    user_id = update.effective_user.id
    
    # Check if user is owner
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ **Access Denied!**\nThis command is for owner only.")
        return
    
    total_users, verified_users = db.get_user_stats()
    
    # Get more detailed stats
    current_time = datetime.now()
    active_users = 0
    for uid, data in db.users.items():
        last_check = datetime.fromisoformat(data.get('last_check', '2000-01-01'))
        if current_time - last_check < timedelta(hours=24):
            active_users += 1
    
    stats_text = f"""📊 **BOT STATISTICS**

👥 **Users:**
├ Total: {total_users}
├ Verified: {verified_users}
├ Unverified: {total_users - verified_users}
└ Active (24h): {active_users}

⚙️ **System:**
├ Check Interval: {CHECK_INTERVAL}s
├ API URL: {API_BASE_URL}
├ Endpoint: {API_ENDPOINT}
└ Database: {DATABASE_FILE}

⏰ **Last Update:** {datetime.now().strftime('%d %b %Y, %I:%M %p')}
"""
    await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all users (admin only)"""
    user_id = update.effective_user.id
    
    # Check if user is owner
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ **Access Denied!**")
        return
    
    # Get broadcast message
    if not context.args:
        await update.message.reply_text(
            "Usage: /broadcast Your message here\n\n"
            "Example: /broadcast Bot will be down for maintenance"
        )
        return
    
    message = " ".join(context.args)
    
    # Send confirmation
    confirm_msg = await update.message.reply_text(
        f"📢 **Broadcasting to {len(db.users)} users...**\n\n"
        f"Message: {message}\n\n"
        f"This may take a few minutes."
    )
    
    # Broadcast to all verified users
    sent = 0
    failed = 0
    
    for uid_str, user_data in db.users.items():
        if user_data.get('verified', False):
            try:
                await context.bot.send_message(
                    chat_id=int(uid_str),
                    text=f"📢 **BROADCAST MESSAGE**\n\n{message}\n\n- @{OWNER_USERNAME}"
                )
                sent += 1
            except Exception as e:
                failed += 1
                logger.error(f"Failed to send to {uid_str}: {e}")
            
            # Small delay to avoid flooding
            await asyncio.sleep(0.05)
    
    await confirm_msg.edit_text(
        f"✅ **Broadcast Complete!**\n\n"
        f"📨 Sent: {sent}\n"
        f"❌ Failed: {failed}\n"
        f"👥 Total users: {len(db.users)}"
    )

async def handle_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle UID messages"""
    uid = update.message.text.strip()
    
    # Check verification first
    if not await verify_user(update, context):
        return
    
    # Validate UID
    if not uid.isdigit():
        await update.message.reply_text(
            "❌ **Invalid UID!**\n"
            "Please enter only numbers.\n"
            "Example: `1484443876`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    if len(uid) < 5 or len(uid) > 15:
        await update.message.reply_text(
            "❌ **Invalid UID length!**\n"
            "Free Fire UID should be 5-15 digits.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Send waiting message
    wait_msg = await update.message.reply_text(
        f"🔍 **Searching for UID:** `{uid}`\n"
        f"⏳ Please wait...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # Fetch data from API
        result = await fetch_player_data(uid)
        
        if result and result.get("success"):
            # Format profile
            profile = format_profile(result, uid)
            
            if profile:
                # Create inline keyboard
                keyboard = [
                    [
                        InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{uid}"),
                        InlineKeyboardButton("📊 Another", callback_data="new_search")
                    ],
                    [
                        InlineKeyboardButton("📢 Channel", url=REQUIRED_CHANNELS[0]['url']),
                        InlineKeyboardButton("👤 Owner", url=f"https://t.me/{OWNER_USERNAME}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Edit waiting message with profile
                await wait_msg.edit_text(
                    profile,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
            else:
                await wait_msg.edit_text(
                    f"❌ **Failed to format data for UID:** `{uid}`\n"
                    f"This might be due to API format mismatch.",
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            error_msg = result.get("error", "Unknown error") if result else "No response from API"
            await wait_msg.edit_text(
                f"❌ **Error fetching data for UID:** `{uid}`\n\n"
                f"🔴 **Reason:** {error_msg}\n\n"
                f"💡 Please check the UID and try again.",
                parse_mode=ParseMode.MARKDOWN
            )
            
    except Exception as e:
        logger.error(f"UID handler error: {e}")
        await wait_msg.edit_text(
            f"❌ **Unexpected error!**\n\n"
            f"Error: {str(e)[:100]}\n\n"
            f"Please try again later.",
            parse_mode=ParseMode.MARKDOWN
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "verify_now":
        # Check verification again
        if await check_membership(query.from_user.id, context):
            db.set_verified(query.from_user.id, True)
            await query.edit_message_text(
                "✅ **Verification Successful!**\n\n"
                "You can now use the bot.\n"
                "Send any Free Fire UID to get info.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await query.edit_message_text(
                "❌ **Verification Failed!**\n\n"
                "You haven't joined both channels yet.\n"
                "Please join both channels and try again.",
                parse_mode=ParseMode.MARKDOWN
            )
            # Show channels again
            await show_verify_required(update, context)
    
    elif data == "help":
        help_text = """❓ **HOW TO USE**

1️⃣ **Join Channels:**
   - Join both required channels
   
2️⃣ **Send UID:**
   - Type any Free Fire UID
   - Example: `1484443876`
   
3️⃣ **Get Info:**
   - Bot fetches from API
   - Shows complete profile

**Need help?**
Contact: @developer_apon
"""
        await query.edit_message_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    elif data == "new_search":
        await query.edit_message_text(
            "🔍 **Send any Free Fire UID**\n\n"
            "Example: `1484443876`",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data.startswith("refresh_"):
        uid = data.replace("refresh_", "")
        
        # Update message
        await query.edit_message_text(
            f"🔄 **Refreshing data for UID:** `{uid}`\n"
            f"⏳ Please wait...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Fetch fresh data
        result = await fetch_player_data(uid)
        
        if result and result.get("success"):
            profile = format_profile(result, uid)
            
            if profile:
                keyboard = [
                    [
                        InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{uid}"),
                        InlineKeyboardButton("📊 Another", callback_data="new_search")
                    ],
                    [
                        InlineKeyboardButton("📢 Channel", url=REQUIRED_CHANNELS[0]['url']),
                        InlineKeyboardButton("👤 Owner", url=f"https://t.me/{OWNER_USERNAME}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    profile,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
            else:
                await query.edit_message_text(
                    f"❌ **Failed to refresh data for UID:** `{uid}`",
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            await query.edit_message_text(
                f"❌ **Failed to refresh UID:** `{uid}`\n"
                f"Please try again.",
                parse_mode=ParseMode.MARKDOWN
            )

# ============================================
# 🚀 MAIN FUNCTION
# ============================================
def main():
    """Main function to start the bot"""
    try:
        # Create application
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Add command handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("about", about_command))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(CommandHandler("broadcast", broadcast_command))
        
        # Add message handler for UIDs
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_uid))
        
        # Add callback query handler for buttons
        app.add_handler(CallbackQueryHandler(button_handler))
        
        # Start bot
        print("🤖 Bot is starting...")
        print(f"👤 Owner ID: {OWNER_ID}")
        print(f"📢 Channels: {len(REQUIRED_CHANNELS)}")
        print(f"🌐 API: {API_BASE_URL}{API_ENDPOINT}")
        print("✅ Bot is running! Press Ctrl+C to stop.")
        
        app.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
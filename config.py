# ============================================
# 🔧 CONFIGURATION FILE - CHANGE ONLY HERE
# ============================================

# Telegram Bot Token (Get from @BotFather)
BOT_TOKEN = "8681688540:AAGQeIRxxLrb6JgMG8Q1eM9Fx808EBLUcvQ"

# Your Personal Information
OWNER_ID = 6678577936  # Your user ID
OWNER_USERNAME = "developer_apon"  # Your username

# -------------------------------
# 📢 VERIFICATION CHANNELS (2 channels)
# -------------------------------
REQUIRED_CHANNELS = [
    {
        "username": "developer_apon_07",  # Channel 1
        "url": "https://t.me/developer_apon_07",
        "name": "Apon Developers Hub 💻"
    },
    {
        "username": "fftigerteamguild",  # Channel 2
        "url": "https://t.me/fftigerteamguild",
        "name": "FF Tiger Team Guild"
    }
]

# -------------------------------
# 🌐 API CONFIGURATION (Put your API here)
# -------------------------------
API_BASE_URL = "https://kallu-ff-info-api.vercel.app"  # Your API URL
API_ENDPOINT = "/accinfo"  # API endpoint
API_KEY = "KALLUxINFO"  # Your API key (if required)

# API Parameters
API_PARAMS = {
    "uid": None,  # None means it will be dynamic
    "key": API_KEY
}

# -------------------------------
# 🎯 API RESPONSE MAPPING (Configure according to your API)
# -------------------------------
API_MAPPING = {
    "success_key": "success",      # Success key in response
    "data_key": "data",            # Main data key
    "error_key": "error",          # Error message key
    
    # Player data mapping
    "player": {
        "nickname": "nickname",     # Put your API field names here
        "level": "level",
        "uid": "uid",
        "likes": "likes",
        "region": "region",
        "guild": "guild",
        "br_rank": "br_rank",
        "cs_rank": "cs_rank",
        "avatar": "avatar",
        "bio": "bio",
        "badges": "badges",
        "honor_score": "honor_score",
        "created_at": "created_at",
        "last_login": "last_login"
    }
}

# Other Settings
CHECK_INTERVAL = 300  # Verification check interval (seconds)
DATABASE_FILE = "users.json"  # User database file

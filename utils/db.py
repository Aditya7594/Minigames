from pymongo import MongoClient
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Connection String
# PRO TIP: In a real production app, use environment variables!
MONGO_URI = 'mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot'

try:
    client = MongoClient(MONGO_URI)
    db = client['telegram_bot']
    
    # Collections
    users_collection = db['users']
    genshin_collection = db['genshin_users']
    groups_collection = db['groups']
    group_settings_collection = db['group_settings']
    shop_collection = db['shop']
    limbo_games_collection = db['limbo_games']
    multiplayer_games_collection = db['multiplayer_games']
    wordhunt_scores_collection = db['wordhunt_scores']
    wordle_scores_collection = db['wordle_scores']
    cricket_games_collection = db['games']
    cricket_persistence_collection = db['cricket_games']
    achievements_collection = db['achievements']
    
    logger.info("Successfully connected to MongoDB.")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    raise e

# Helper functions can be added here
def get_user_by_id(user_id):
    return users_collection.find_one({"user_id": str(user_id)})

def save_user(user_data):
    users_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

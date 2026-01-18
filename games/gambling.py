import random
import logging
import asyncio
from datetime import datetime, timezone
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext
from pymongo import DESCENDING
from utils.db import get_user_by_id, save_user, users_collection

logger = logging.getLogger(__name__)

def get_ist_time():
    """Get current time in IST with proper timezone handling."""
    utc_now = datetime.now(timezone.utc)
    ist = pytz.timezone('Asia/Kolkata')
    ist_time = utc_now.astimezone(ist)
    return ist_time.strftime("%H:%M:%S IST")

async def bet(update: Update, context: CallbackContext) -> None:
    """Handle the /bet command for betting credits."""
    user = update.effective_user
    user_id = str(user.id)
    
    # Check if amount is provided
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "Usage: /bet <amount>\n"
            "Example: /bet 100"
        )
        return
    
    amount = int(context.args[0])
    if amount <= 0:
        await update.message.reply_text("Please bet a positive amount.")
        return
        
    # Check maximum bet limit
    if amount > 50000:
        await update.message.reply_text("Maximum bet limit is 50,000 credits.")
        return
    
    # Get user data
    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first using /start.")
        return
    
    # Check if user has enough credits
    if user_data.get('credits', 0) < amount:
        await update.message.reply_text(f"You don't have enough credits. Your balance: {user_data.get('credits', 0)}")
        return
    
    # Generate random number between 1 and 100
    result = random.randint(1, 100)
    
    # 50% chance to win
    if result <= 50:
        # Win
        winnings = amount * 2
        user_data['credits'] += amount
        user_data['win'] = user_data.get('win', 0) + 1
        message = f"🎉 You won {winnings} credits!"
    else:
        # Lose
        user_data['credits'] -= amount
        user_data['loss'] = user_data.get('loss', 0) + 1
        message = f"😢 You lost {amount} credits!"
    
    # Save updated user data
    save_user(user_data)
    
    # Send result
    await update.message.reply_text(
        f"{message}\n"
        f"Your new balance: {user_data['credits']} credits"
    )

async def flip(update: Update, context: CallbackContext) -> None:
    """Handle the /flip command for betting on coin flip."""
    user = update.effective_user
    user_id = str(user.id)
    
    # Check if choice and amount are provided
    if not context.args or len(context.args) != 2:
        await update.message.reply_text(
            "Usage: /flip <h/t> <amount>\n"
            "Example: /flip h 100"
        )
        return
    
    choice = context.args[0].lower()
    if choice not in ['h', 't']:
        await update.message.reply_text("Please choose 'h' for heads or 't' for tails.")
        return
    
    if not context.args[1].isdigit():
        await update.message.reply_text("Please provide a valid amount.")
        return
    
    amount = int(context.args[1])
    if amount <= 0:
        await update.message.reply_text("Please bet a positive amount.")
        return
    
    # Get user data
    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first using /start.")
        return
    
    # Check if user has enough credits
    if user_data.get('credits', 0) < amount:
        await update.message.reply_text(f"You don't have enough credits. Your balance: {user_data.get('credits', 0)}")
        return
    
    # Get current IST time
    current_time = get_ist_time()
    
    # Flip coin
    result = random.choice(['h', 't'])
    result_text = 'Heads' if result == 'h' else 'Tails'
    
    # Check if user won
    if choice == result:
        # Win
        winnings = amount * 2
        user_data['credits'] += amount
        user_data['win'] = user_data.get('win', 0) + 1
        message = f"🎉 You won {winnings} credits!"
    else:
        # Lose
        user_data['credits'] -= amount
        user_data['loss'] = user_data.get('loss', 0) + 1
        message = f"😢 You lost {amount} credits!"
    
    # Save updated user data
    save_user(user_data)
    
    # Send result with HTML formatting
    await update.message.reply_text(
        f"🪙 <b>Coin Flip Result</b>\n\n"
        f"👤 User: {user.first_name}\n"
        f"⏰ Time: {current_time}\n"
        f"🎲 Result: {result_text}\n"
        f"💰 {message}\n"
        f"💳 New Balance: {user_data['credits']} credits",
        parse_mode='HTML'
    )

async def toss(update: Update, context: CallbackContext) -> None:
    """Handle the /toss command for simple coin flip."""
    user = update.effective_user
    
    # Get current IST time
    current_time = get_ist_time()
    
    # Flip coin
    result = random.choice(['Heads', 'Tails'])
    
    # Send result
    await update.message.reply_text(
        f"{user.first_name} flipped a coin!\n\n"
        f"It's {result}! {current_time}"
    )

async def dice(update: Update, context: CallbackContext) -> None:
    """Handle the /dice command for rolling dice."""
    user = update.effective_user
    user_id = str(user.id)
    
    # Check if amount is provided
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "Usage: /dice <amount>\n"
            "Example: /dice 100"
        )
        return
    
    amount = int(context.args[0])
    if amount <= 0:
        await update.message.reply_text("Please bet a positive amount.")
        return
    
    # Get user data
    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first using /start.")
        return
    
    # Check if user has enough credits
    if user_data.get('credits', 0) < amount:
        await update.message.reply_text(f"You don't have enough credits. Your balance: {user_data.get('credits', 0)}")
        return
    
    # Roll dice (1-6)
    result = random.randint(1, 6)
    
    # Win if roll is 4 or higher (50% chance)
    if result >= 4:
        # Win
        winnings = amount * 2
        user_data['credits'] += amount
        user_data['win'] = user_data.get('win', 0) + 1
        message = f"🎉 You won {winnings} credits!"
    else:
        # Lose
        user_data['credits'] -= amount
        user_data['loss'] = user_data.get('loss', 0) + 1
        message = f"😢 You lost {amount} credits!"
    
    # Save updated user data
    save_user(user_data)
    
    # Send result
    await update.message.reply_text(
        f"🎲 <b>Dice Roll</b>\n\n"
        f"👤 User: {user.first_name}\n"
        f"🎯 Roll: {result}\n"
        f"💰 {message}\n"
        f"💳 New Balance: {user_data['credits']} credits",
        parse_mode='HTML'
    )

async def cleaderboard(update: Update, context: CallbackContext) -> None:
    """Show the top 25 users by credits."""
    try:
        # Get top 25 users by credits using the imported collection
        top_users = list(users_collection.find().sort("credits", DESCENDING).limit(25))
        
        if not top_users:
            await update.message.reply_text("No users found in the leaderboard.")
            return
        
        # Create leaderboard message
        leaderboard = "🏆 <b>Credits Leaderboard</b>\n\n"
        
        for i, user in enumerate(top_users, 1):
            user_id = user.get('user_id')
            credits = user.get('credits', 0)
            
            # Try to get user name from multiple sources in order of preference
            name = None
            if user.get('first_name'):
                name = user['first_name']
            elif user.get('username'):
                name = f"@{user['username']}"
            elif user.get('name'):
                name = user['name']
            
            # If still no name, try to fetch from Telegram (only for top users to avoid rate limits)
            if not name and user_id and i <= 10:  # Only fetch for top 10 users
                try:
                    user_id_int = int(user_id)
                    chat_member = await context.bot.get_chat(user_id_int)
                    name = chat_member.first_name or chat_member.username or f"User{user_id_int}"
                    
                    # Update the database with the fresh name
                    if name and name != f"User{user_id_int}":
                        update_data = {}
                        if chat_member.first_name:
                            update_data['first_name'] = chat_member.first_name
                        if chat_member.username:
                            update_data['username'] = chat_member.username
                        if update_data:
                            users_collection.update_one(
                                {"user_id": user_id},
                                {"$set": update_data}
                            )
                    
                    # Small delay to avoid rate limits
                    await asyncio.sleep(0.1)
                            
                except Exception as e:
                    logger.debug(f"Could not fetch user {user_id_int} from Telegram: {e}")
                    # If we can't fetch from Telegram, use a fallback
                    name = f"User{user_id_int}" if user_id_int else "Unknown"
            
            # Final fallback
            if not name:
                name = "Unknown"
            
            leaderboard += f"{i}. {name}: {credits:,} credits\n"
        
        await update.message.reply_text(leaderboard, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error in cleaderboard: {e}")
        await update.message.reply_text("Failed to retrieve the leaderboard. Please try again later.")

async def refresh_names(update: Update, context: CallbackContext) -> None:
    """Refresh user names in the database by fetching from Telegram."""
    # Check if user is owner/admin
    user_id = update.effective_user.id
    if user_id != 5667016949:  # Owner ID
        await update.message.reply_text("❌ You don't have permission to use this command.")
        return
    
    try:
        await update.message.reply_text("🔄 Refreshing user names from Telegram...")
        
        # Get all users from database
        all_users = list(users_collection.find({}))
        updated_count = 0
        
        for user in all_users:
            user_id_str = user.get('user_id')
            if not user_id_str:
                continue
                
            try:
                user_id_int = int(user_id_str)
                chat_member = await context.bot.get_chat(user_id_int)
                
                # Update user data with fresh information
                update_data = {}
                if chat_member.first_name:
                    update_data['first_name'] = chat_member.first_name
                if chat_member.username:
                    update_data['username'] = chat_member.username
                if chat_member.last_name:
                    update_data['last_name'] = chat_member.last_name
                
                if update_data:
                    users_collection.update_one(
                        {"user_id": user_id_str},
                        {"$set": update_data}
                    )
                    updated_count += 1
                    
            except Exception as e:
                logger.debug(f"Could not update user {user_id_str}: {e}")
                continue
        
        await update.message.reply_text(f"✅ Successfully updated {updated_count} user names!")
        
    except Exception as e:
        logger.error(f"Error in refresh_names: {e}")
        await update.message.reply_text("❌ Failed to refresh user names. Please try again later.")

def get_gambling_handlers():
    """Return all gambling-related command handlers."""
    return [
        CommandHandler("bet", bet),
        CommandHandler("flip", flip),
        CommandHandler("toss", toss),
        CommandHandler("dice", dice),
        CommandHandler("cleaderboard", cleaderboard),
        CommandHandler("refreshnames", refresh_names)
    ] 

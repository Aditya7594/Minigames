import os
import random
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from datetime import datetime
from utils.db import users_collection, get_user_by_id, save_user

# Game Configuration
CARD_VALUES = {'A': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13}
SUITS = ['diamonds', 'hearts', 'clubs', 'spades']
DECK = [(suit, value) for suit in SUITS for value in CARD_VALUES.keys()]

# Enhanced Game State Management
class HiLoGameManager:
    def __init__(self):
        self.games = {}
        self.daily_limits = {}
        self.max_daily_games = 50
        self.min_bet = 100
        self.max_bet = 10000
        self.base_multiplier = 1.0
        self.multiplier_increment = 0.5
        self.max_multiplier = 5.0

    def get_user_data(self, user_id):
        # Use centralized DB utility
        user = get_user_by_id(user_id)
        if not user:
            # Create user if not exists (though typically they should exist)
            user = {
                "user_id": str(user_id),
                "credits": 1000, # Starting credits if new
                "first_name": "Unknown"
            }
            save_user(user)
        return user

    def update_user_credits(self, user_id, credits):
        users_collection.update_one({"user_id": str(user_id)}, {"$set": {"credits": credits}})

    def can_play_game(self, user_id):
        if user_id not in self.daily_limits:
            self.daily_limits[user_id] = 0
        return self.daily_limits[user_id] < self.max_daily_games

    def start_game(self, user_id, bet):
        player_card = random.choice(DECK)
        self.games[user_id] = {
            "bet": bet,
            "player_card": player_card,
            "multiplier": self.base_multiplier,
            "rounds_played": 0
        }
        return player_card

    def process_guess(self, user_id, guess):
        game = self.games.get(user_id)
        if not game:
            return None, None, None

        player_card = game["player_card"]
        table_card = random.choice(DECK)
        
        player_value = CARD_VALUES[player_card[1]]
        table_value = CARD_VALUES[table_card[1]]

        # Determine if guess is correct
        is_correct = (guess == "high" and table_value > player_value) or \
                     (guess == "low" and table_value < player_value)

        if is_correct:
            # Increase multiplier with diminishing returns
            game["multiplier"] = min(
                self.base_multiplier + (game["rounds_played"] * self.multiplier_increment), 
                self.max_multiplier
            )
            game["player_card"] = table_card
            game["rounds_played"] += 1
        
        return is_correct, table_card, game["multiplier"]

    def end_game(self, user_id):
        """Ends the game and returns the final stats before deletion."""
        game = self.games.get(user_id)
        if not game:
            return None
        
        # Calculate winnings based on current state
        winnings = round(game["bet"] * game["multiplier"])
        
        # Capture stats
        stats = {
            "bet": game["bet"],
            "multiplier": game["multiplier"],
            "winnings": winnings
        }
        
        # Cleanup
        del self.games[user_id]
        if user_id not in self.daily_limits:
             self.daily_limits[user_id] = 0
        self.daily_limits[user_id] += 1
        return stats

# Resize card image function
def resize_card_image(card):
    suit, value = card
    # Path relative to this file: ../assets/images/playingcards
    # Using absolute logic based on project root is safer if CWD varies, but __file__ is robust.
    # The user said playingcards is in assets/images/playingcards.
    folder_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "images", "playingcards")
    filename = f"{suit.lower()}_{value}.png"
    path = os.path.join(folder_path, filename)

    if not os.path.exists(path):
        # Fallback or error? Let's check if the folder exists at all.
        if not os.path.exists(folder_path):
             # Try simpler path if running from root
             folder_path = os.path.abspath("assets/images/playingcards")
             path = os.path.join(folder_path, filename)
             
        if not os.path.exists(path):
            raise FileNotFoundError(f"Card image not found: {path}")

    # Create resized version
    resized_filename = f"resized_{suit.lower()}_{value}.png"
    resized_path = os.path.join(folder_path, resized_filename)
    
    if not os.path.exists(resized_path):
        try:
            with Image.open(path) as img:
                img.thumbnail((200, 300))  # Resize to smaller dimensions
                img.save(resized_path)
        except Exception as e:
            # If resizing fails, return original (might be too big but better than crash)
            return path
            
    return resized_path

# Initialize game manager
game_manager = HiLoGameManager()

# Start HiLo game
async def start_hilo(update: Update, context):
    """Start a new HiLo game."""
    # Removed private chat restriction
    user_id = str(update.effective_user.id)
    user_data = game_manager.get_user_data(user_id)
    
    # Check for bet amount in command
    bet_amount = 0
    if context.args:
        try:
            bet_amount = int(context.args[0])
            if bet_amount < game_manager.min_bet:
                await update.message.reply_text(f"Minimum bet amount is {game_manager.min_bet} credits!")
                return
            if bet_amount > game_manager.max_bet:
                await update.message.reply_text(f"Maximum bet amount is {game_manager.max_bet} credits!")
                return
            if user_data.get('credits', 0) < bet_amount:
                await update.message.reply_text(f"You need at least {bet_amount} credits to start a game with this bet!")
                return
        except ValueError:
            await update.message.reply_text("Please provide a valid number for the bet amount!")
            return
    
    # If no bet provided, imply a default or ask? Original code allowed 0 (logic: if context.args). 
    # But later `self.start_game(user_id, bet_amount)` uses 0 if no args. 
    # Can you bet 0? `process_guess` multipliers on 0 is 0. 
    # For a real game, let's enforce min bet or default. 
    # Original code: `bet_amount = 0` initialized. If no args, starts with 0. 
    # This might be "practice" mode. I'll preserve that behavior.
    
    # Check daily game limit
    if not game_manager.can_play_game(user_id):
        await update.message.reply_text(f"You've reached the daily limit of {game_manager.max_daily_games} games!")
        return
    
    # Start the game
    player_card = game_manager.start_game(user_id, bet_amount)
    
    # Create keyboard
    keyboard = [
        [
            InlineKeyboardButton("⬇️ Lower", callback_data=f"hilo_low_{user_id}"),
            InlineKeyboardButton("⬆️ Higher", callback_data=f"hilo_high_{user_id}")
        ],
        [InlineKeyboardButton("💰 Cashout", callback_data=f"hilo_cashout_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send game start message with card image
    try:
        card_path = resize_card_image(player_card)
        with open(card_path, 'rb') as card_file:
            await update.message.reply_photo(
                photo=card_file,
                caption=(
                    f"🎴 *HiLo Game Started!* 🎴\n\n"
                    f"Your card: {player_card[1]} of {player_card[0]}\n"
                    f"Current multiplier: {game_manager.base_multiplier}x"
                ),
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
    except Exception as e:
        await update.message.reply_text(
            f"🎴 *HiLo Game Started!* 🎴\n\n"
            f"Your card: {player_card[1]} of {player_card[0]}\n"
            f"Current multiplier: {game_manager.base_multiplier}x\n"
            f"(Image failed to load: {e})",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

# Handle HiLo choices
async def hilo_click(update: Update, context):
    """Handle HiLo game button clicks."""
    query = update.callback_query
    user_id = str(update.effective_user.id)
    
    try:
        action, owner_id = query.data.split('_')[1], query.data.split('_')[-1]
    except ValueError:
        await query.answer("Invalid request")
        return

    # Verify user ownership of the game
    if user_id != owner_id:
        await query.answer("This is not your game!", show_alert=True)
        return
    
    # Process the guess
    is_correct, table_card, multiplier = game_manager.process_guess(user_id, action)
    
    if is_correct is None:
        await query.answer("Game not found or expired!")
        # Optional: Edit message to show expired
        return
    
    # Create keyboard for next move
    keyboard = [
        [
            InlineKeyboardButton("⬇️ Lower", callback_data=f"hilo_low_{user_id}"),
            InlineKeyboardButton("⬆️ Higher", callback_data=f"hilo_high_{user_id}")
        ],
        [InlineKeyboardButton("💰 Cashout", callback_data=f"hilo_cashout_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if is_correct:
        # Correct guess - show new card and continue
        try:
            card_path = resize_card_image(table_card)
            with open(card_path, 'rb') as card_file:
                # Use InputMediaPhoto to edit just the media
                await query.message.edit_media(
                    media=InputMediaPhoto(
                        media=card_file,
                        caption=(
                            f"🎴 *Correct!* 🎴\n\n"
                            f"Your card: {table_card[1]} of {table_card[0]}\n"
                            f"Current multiplier: {multiplier:.1f}x"
                        ),
                        parse_mode="Markdown"
                    ),
                    reply_markup=reply_markup
                )
        except Exception as e:
             await query.message.edit_caption(
                caption=(
                    f"🎴 *Correct!* 🎴\n\n"
                    f"Your card: {table_card[1]} of {table_card[0]}\n"
                    f"Current multiplier: {multiplier:.1f}x"
                ),
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
    else:
        # Wrong guess - game over (Lost)
        await hilo_cashout(update, context, lost=True)

# Handle Cash Out
async def hilo_cashout(update: Update, context, lost=False):
    """Handle HiLo game cashout."""
    query = update.callback_query
    user_id = str(update.effective_user.id)
    
    try:
        # data format example: hilo_cashout_12345
        owner_id = query.data.split('_')[-1]
    except:
        owner_id = user_id # Fallback
        
    if user_id != owner_id:
        await query.answer("This is not your game!", show_alert=True)
        return
    
    # End game and get stats BEFORE responding
    stats = game_manager.end_game(user_id)
    
    if not stats:
        await query.answer("Game already ended!")
        return

    bet = stats["bet"]
    multiplier = stats["multiplier"]
    winnings = stats["winnings"]
    
    # Update credits
    message_top = "🎴 *HiLo Game Over!* 🎴\n\n"
    message_content = f"Final multiplier: {multiplier:.1f}x"
    
    if lost:
        # If lost, winnings are 0, and they already paid the bet? 
        # Wait, implementation of start_game didn't deduct bet!
        # Reference `bdice.py`: deducted upfront. 
        # Here: `start_hilo` checks funds but DOES NOT deduct.
        # So on loss, we must deduct. Or on start we deduct?
        # Original code line 260 implies: "You lost {bet} credits". 
        # But `calculate_winnings` only handled winnings.
        # If I change to deduct on start, it's safer.
        # BUT refactoring logic now: 
        # Let's deduct on LOSS for now to match implicit logic, OR deduct on WIN (net change)?
        # If I don't deduct on start:
        # - WIN: Add (Bet * Multiplier) - Bet? No, usually "Winnings" is total return?
        # - LOSS: Subtract Bet.
        
        user_data = game_manager.get_user_data(user_id)
        current_credits = user_data.get('credits', 0)
        
        # Deduct bet on loss
        if bet > 0:
            new_credits = max(0, current_credits - bet)
            game_manager.update_user_credits(user_id, new_credits)
            message_content += f"\n❌ You lost {bet} credits!"
            
    else: # Won / Cashed out
        # If user cashes out, they get their winnings.
        # If they haven't paid "upfront", effectively they just win (Bet * Mult) - Bet?
        # Standard gambling: You bet 100.
        # Win 2x -> You get 200 back (100 profit).
        # Loss -> You lose your 100.
        # If we didn't deduct 100 at start:
        # Cashout 2x: Add 100 (Profit).
        # Loss: Deduct 100.
        
        # Let's assume user kept their money until now.
        if bet > 0:
            user_data = game_manager.get_user_data(user_id)
            profit = winnings - bet
            new_credits = user_data.get('credits', 0) + profit
            game_manager.update_user_credits(user_id, new_credits)
            message_content += f"\n💰 You won {winnings} credits!\n(Profit: {profit})"
            
    # Update message
    full_message = message_top + message_content
    
    try:
        await query.edit_message_caption(caption=full_message, parse_mode="Markdown")
    except:
        await query.edit_message_text(full_message, parse_mode="Markdown")

def get_hilo_handlers():
    """Return all HiLo game handlers."""
    return [
        CommandHandler("hilo", start_hilo),
        CallbackQueryHandler(hilo_click, pattern="^hilo_(low|high)_"),
        CallbackQueryHandler(hilo_cashout, pattern="^hilo_cashout_")
    ]
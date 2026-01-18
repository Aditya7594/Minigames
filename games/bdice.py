from telegram import Update
from telegram.ext import CallbackContext, CommandHandler
import asyncio
from datetime import datetime
from utils.db import get_user_by_id, save_user

async def bdice(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    try:
        if not context.args or len(context.args) < 2:
            raise IndexError
        bet_amount = int(context.args[0])
        user_guess = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /bdice <bet_amount> <your_guess_total (3-18)>")
        return

    # Check if the bet amount is within the maximum limit
    max_bet = 5000
    if bet_amount > max_bet:
        await update.message.reply_text(f"The maximum bet amount is {max_bet} credits.")
        return
    
    if bet_amount <= 0:
        await update.message.reply_text("Bet amount must be positive.")
        return

    if user_guess < 3 or user_guess > 18:
        await update.message.reply_text("Your guess must be between 3 and 18.")
        return

    # Fetch user data
    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to use /start first to register.")
        return

    # Reset bdice_daily count if the day has changed
    today = datetime.now().strftime('%Y-%m-%d')
    if 'bdice_daily' not in user_data or user_data['bdice_daily']['date'] != today:
        user_data['bdice_daily'] = {"date": today, "plays": 0}

    # Check if the user has reached their play limit
    if user_data['bdice_daily']['plays'] >= 20:
        await update.message.reply_text("You've reached your daily limit of 20 plays for /bdice.")
        return

    if user_data.get('credits', 0) < bet_amount:
        await update.message.reply_text("You don't have enough credits for this bet.")
        return

    # Increment daily play count
    user_data['bdice_daily']['plays'] += 1
    
    # Deduct bet amount immediately to prevent double spending
    user_data['credits'] -= bet_amount
    save_user(user_data)

    # Notify the user that the game is in progress
    await update.message.reply_text(f"🎲 Rolling for a bet of {bet_amount}! Guessing: {user_guess}...")

    # Start the dice game as a background task
    asyncio.create_task(process_dice_game(update, user_id, bet_amount, user_guess))


async def process_dice_game(update: Update, user_id: str, bet_amount: int, user_guess: int) -> None:
    # Simulate dice rolls
    dice_results = []
    
    # Send dice animations sequentially
    for _ in range(3):
        msg = await update.message.reply_dice(emoji="🎲")
        dice_results.append(msg.dice.value)
        await asyncio.sleep(2.5)  # Slightly reduced sleep time for better pacing

    # Calculate total dice result
    dice_total = sum(dice_results)

    # Calculate reward multiplier
    difference = abs(user_guess - dice_total)
    multiplier = 0
    
    if difference == 0:
        multiplier = 3
    elif difference <= 1:
        multiplier = 1.5
    elif difference <= 3:
        multiplier = 0.75
    
    winnings = int(bet_amount * multiplier)
    
    # Fetch fresh user data to ensure atomic-like balance update
    user_data = get_user_by_id(user_id)
    if user_data:
        # Credits were already deducted, so we just add winnings
        # If multiplier is 0, they get 0 back (lost bet)
        # If multiplier is 0.75, they get 0.75 * bet back (lost part of bet)
        # However, logic in original code was: user_data['credits'] += winnings - bet_amount
        # But wait! The original code DID NOT deduct the bet upfront!
        # Original: user_data['credits'] += winnings - bet_amount
        # My new logic: Deduct bet upfront. Then add `winnings`.
        # Example: Bet 100. Balance 1000 -> 900.
        # Win (x3): Winnings 300. Balance 900 + 300 = 1200. (Effective +200).
        # Original: Balance 1000. Winnings 300. Balance 1000 + (300 - 100) = 1200.
        # Loss (x0): Winnings 0. Balance 900 + 0 = 900. (Effective -100).
        # Original: Balance 1000. Winnings 0. Balance 1000 + (0 - 100) = 900.
        # It matches!
        
        user_data['credits'] += winnings
        save_user(user_data)
        
        current_credits = user_data['credits']
        daily_plays = user_data.get('bdice_daily', {}).get('plays', 0)

        # Send results
        result_msg = (
            f"🎲 Results: *{dice_results[0]}*, *{dice_results[1]}*, *{dice_results[2]}* → Total: *{dice_total}*\n"
            f"🎯 Your Guess: *{user_guess}*\n"
        )
        
        if winnings > bet_amount:
             result_msg += f"🏆 *BIG WIN!* You won *{winnings}* credits! (x{multiplier})\n"
        elif winnings > 0:
             result_msg += f"✨ You got back *{winnings}* credits. (x{multiplier})\n"
        else:
             result_msg += f"💸 You lost *{bet_amount}* credits.\n"
             
        result_msg += (
            f"💰 Balance: *{current_credits}*\n"
            f"🎮 Plays Today: *{daily_plays}/20*"
        )

        await update.message.reply_text(result_msg, parse_mode="Markdown")

def get_bdice_handlers():
    return [
        CommandHandler("bdice", bdice)
    ]

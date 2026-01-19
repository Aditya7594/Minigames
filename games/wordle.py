from __future__ import annotations

import os
import random
import json
import logging
from collections import Counter
from typing import Sequence, Optional, Dict, Any

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes,
    filters
)
from utils.db import wordle_scores_collection

# Setup logging
logger = logging.getLogger(__name__)

# DB Alias
wordle_col = wordle_scores_collection

# Game constants
ABSENT, PRESENT, CORRECT = 0, 1, 2
BLOCKS = {0: "🟥", 1: "🟨", 2: "🟩"}
MAX_TRIALS = 30  # Standard Wordle is 6 trials, updated to 30

# Load word lists from JSON
WORD_LIST = []
try:
    json_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'word_lists.json')
    logger.info(f"Loading Wordle word list from: {json_path}")
    with open(json_path, 'r') as f:
        _word_data = json.load(f)
        WORD_LIST = _word_data.get('wordle', [])
    logger.info(f"Wordle word list loaded: {len(WORD_LIST)} words")
except FileNotFoundError as e:
    logger.error(f"Word list not found: {e}")
except Exception as e:
    logger.error(f"Error loading word list: {e}")

CRICKET_TERMS = ["stump", "pitch", "creas", "bails", "sweep", "drive", "hook", "pull", 
                "cover", "point", "midon", "midof", "slips", "gully", "third", "fine", 
                "short", "long", "deep", "silly", "york", "bounc", "googl", "doosr",
                "teesr", "swing", "seam", "spin", "armba", "legg", "off", "on", "over",
                "maid", "wide", "nob", "bye", "legb", "wick", "bat", "ball", "field",
                "catch", "bowl", "run", "out", "lbow", "hatt", "cent", "duc", "pair",
                "ton", "fift", "hund", "five", "ten", "six", "four", "two", "one", "zero"]

CRICKET_WORD_LIST = [word.upper() for word in CRICKET_TERMS if len(word) == 5]

# Game state storage
wordle_games: Dict[int, Dict[str, Any]] = {}

def verify_solution(guess: str, solution: str) -> Sequence[int]:
    result = [-1] * len(solution)
    counter = Counter(solution)
    for i, l in enumerate(solution):
        if guess[i] == l:
            result[i] = CORRECT
            counter[l] -= 1
    for i, l in enumerate(guess):
        if result[i] == -1:
            if counter.get(l, 0) > 0:
                result[i] = PRESENT
                counter[l] -= 1
            else:
                result[i] = ABSENT
    return result

def adjust_score(user_id, name, chat_id, points):
    user = wordle_col.find_one({"_id": user_id})
    if not user:
        wordle_col.insert_one({
            "_id": user_id,
            "name": name,
            "points": points,
            "group_points": {str(chat_id): points}
        })
    else:
        new_total = user.get("points", 0) + points
        group_points = user.get("group_points", {})
        group_points[str(chat_id)] = group_points.get(str(chat_id), 0) + points
        wordle_col.update_one(
            {"_id": user_id},
            {"$set": {"points": new_total, "group_points": group_points, "name": name}}
        )

async def wordle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if chat_id in wordle_games:
        await update.message.reply_text("Game already in progress.")
        return

    if not WORD_LIST:
        await update.message.reply_text("Dictionary not available.")
        return

    word = random.choice(WORD_LIST)
    
    wordle_games[chat_id] = {
        'game_active': True,
        'solution': word,
        'attempts': 0,
        'mode': "wordle",
        'guesses': []
    }

    await update.message.reply_text(f"WORDLE started! Guess the 5-letter word. You have {MAX_TRIALS} trials.")

async def cricketwordle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if chat_id in wordle_games:
        await update.message.reply_text("Game already in progress.")
        return

    if not CRICKET_WORD_LIST:
        await update.message.reply_text("Cricket terms not available.")
        return

    word = random.choice(CRICKET_WORD_LIST)
    
    wordle_games[chat_id] = {
        'game_active': True,
        'solution': word,
        'attempts': 0,
        'mode': "cricketwordle",
        'guesses': []
    }

    await update.message.reply_text(f"CRICKETWORDLE started! Guess the 5-letter cricket term. You have {MAX_TRIALS} trials.")

async def handle_guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    logger.info(f"Wordle handle_guess called for chat {chat_id}, message: {update.message.text}")
    if chat_id not in wordle_games:
        logger.info(f"No active Wordle game in chat {chat_id}")
        return

    game = wordle_games[chat_id]
    user = update.effective_user
    guess = update.message.text.strip().upper()
    solution = game['solution']
    
    word_list = CRICKET_WORD_LIST if game['mode'] == 'cricketwordle' else WORD_LIST

    previous_guess_words = [entry.split()[-1].upper() for entry in game['guesses']]
    if guess in previous_guess_words:
        await update.message.reply_text("You already tried that word!")
        return

    if len(guess) != len(solution):
        await update.message.reply_text(f"Word must be {len(solution)} letters.")
        return
    
    if guess not in word_list:
        await update.message.reply_text("Word not in dictionary.")
        return

    game['attempts'] += 1
    result = verify_solution(guess, solution)
    result_blocks = "".join(BLOCKS[r] for r in result)

    game['guesses'].append(f"{result_blocks}   {guess}")
    adjust_score(user.id, user.first_name, chat_id, 1)

    board_display = "\n".join(game['guesses'])

    if all(r == CORRECT for r in result):
        board_display += f"\n🎉 You won in {game['attempts']} tries!"
        adjust_score(user.id, user.first_name, chat_id, 20)
        del wordle_games[chat_id]
    elif game['attempts'] >= MAX_TRIALS:
        board_display += f"\n❌ Out of tries ({MAX_TRIALS}). The word was: {solution}"
        del wordle_games[chat_id]

    await update.message.reply_text(board_display)

async def wordleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    pipeline = [
        {"$project": {"name": {"$ifNull": ["$name", "Anonymous"]}, "points": {"$ifNull": [f"$group_points.{chat_id}", 0]}}},
        {"$match": {"points": {"$gt": 0}}},
        {"$sort": {"points": -1}},
        {"$limit": 10}
    ]
    top = list(wordle_col.aggregate(pipeline))
    msg = "🏅 Group Wordle Leaderboard:\n\n"
    for i, user in enumerate(top, 1):
        msg += f"{i}. {user['name']} - {user.get('points', 0)} pts\n"
    await update.message.reply_text(msg.strip() or "No leaderboard data.")

async def wordglobal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    top = list(wordle_col.find().sort("points", -1).limit(10))
    msg = "🌍 Global Wordle Leaderboard:\n\n"
    for i, user in enumerate(top, 1):
        msg += f"{i}. {user.get('name', 'Anonymous')} - {user.get('points', 0)} pts\n"
    await update.message.reply_text(msg.strip() or "No leaderboard data.")

async def end_wordle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if chat_id not in wordle_games:
        await update.message.reply_text("No active Wordle game to end.")
        return
    
    solution = wordle_games[chat_id]['solution']
    del wordle_games[chat_id]
    await update.message.reply_text(f"Game ended! The word was: {solution.upper()}")

class ActiveWordleFilter(filters.MessageFilter):
    def filter(self, message):
        chat_id = message.chat_id
        return chat_id in wordle_games and wordle_games[chat_id]['game_active']

active_wordle_filter = ActiveWordleFilter()

def registers_handlers(application: Application) -> list:
    handlers = [
        CommandHandler("wordle", wordle),
        CommandHandler("cricketwordle", cricketwordle),
        CommandHandler("wordleaderboard", wordleaderboard),
        CommandHandler("wordglobal", wordglobal),
        CommandHandler("endwordle", end_wordle),
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.ChatType.PRIVATE,
            handle_guess,
            block=False
        )
    ]
    return handlers

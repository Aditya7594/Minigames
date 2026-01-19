from __future__ import annotations

import os
import random
import asyncio
import json
import logging
from collections import defaultdict
from typing import Dict, Any

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes,
    filters
)
from utils.db import wordhunt_scores_collection

# Setup logging
logger = logging.getLogger(__name__)

# DB Alias
wh_scores = wordhunt_scores_collection

# Game constants
MAX_TRIALS = 25

# Load word list from JSON
wordhunt_word_list = []
try:
    json_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'word_lists.json')
    logger.info(f"Loading WordHunt word list from: {json_path}")
    with open(json_path, 'r') as f:
        _word_data = json.load(f)
        wordhunt_word_list = _word_data.get('wordhunt', [])
    logger.info(f"WordHunt word list loaded: {len(wordhunt_word_list)} words")
except FileNotFoundError as e:
    logger.error(f"Word list not found: {e}")
except Exception as e:
    logger.error(f"Error loading word list: {e}")

# Game state storage
wordhunt_games = {}
activity_timers = {}  # Store activity timers for wordhunt

def upper_letters(letter_row):
    """Format letter row for display"""
    return " ".join(letter.upper() for letter in letter_row)

async def update_wordhunt_score(group_id, player_name, score):
    """Update user score in MongoDB for WordHunt games"""
    try:
        wh_scores.update_one(
            {"group_id": group_id, "player_name": player_name},
            {"$inc": {"score": score}},
            upsert=True
        )
    except Exception as e:
        print(f"Error updating score: {e}")

class WordHuntGame:
    """Class to represent a WordHunt game"""
    
    def __init__(self):
        self.line_list = wordhunt_word_list.copy()
        self.ongoing_game = False
        self.letter_row = []
        self.score_words = []
        self.found_words = []
        self.player_scores = {}
        self.top_score_words = []
        self.player_words = {}
        self.last_activity_time = None

    def create_letter_row(self):
        vowels = ['a','e','i','o','u']
        non_vowels_common = ['b', 'c', 'd', 'f', 'g', 'h', 'k', 'l', 'm', 'n', 'p', 'r', 's', 't','w','y']
        non_vowels_rare = ['j', 'q', 'x', 'z','v']
        num_vowels = random.randint(2,3)
        self.letter_row = []
        for i in range(num_vowels):
            self.letter_row.append(random.choice(vowels))
        for j in range(7 - num_vowels):
            self.letter_row.append(random.choice(non_vowels_common))
        self.letter_row.append(random.choice(non_vowels_rare))
        random.shuffle(self.letter_row)

    async def create_score_words(self):
        """Find valid words that can be spelled with the letter row"""
        self.score_words = []
        letter_counts = defaultdict(int)
        for letter in self.letter_row:
            letter_counts[letter.lower()] += 1
        
        # Process in chunks to avoid blocking
        chunk_size = 1000
        for i, word in enumerate(self.line_list):
            word_lower = word.lower()
            temp_counts = letter_counts.copy()
            valid = True
            
            for letter in word_lower:
                if temp_counts[letter] <= 0:
                    valid = False
                    break
                temp_counts[letter] -= 1
                
            if valid:
                self.score_words.append(word)
            
            # Yield control every chunk_size words to prevent CPU blocking
            if i % chunk_size == 0:
                await asyncio.sleep(0)

    def can_spell(self, word):
        """Check if a word can be spelled with the current letters"""
        word_letters = list(word.lower())
        available_letters = [letter.lower() for letter in self.letter_row]
        
        letter_counts = defaultdict(int)
        for letter in available_letters:
            letter_counts[letter] += 1
            
        for letter in word_letters:
            if letter_counts[letter] <= 0:
                return False
            letter_counts[letter] -= 1
        return True

    async def start(self):
        """Start a new game with at least 35 possible words"""
        if not self.ongoing_game:
            self.ongoing_game = True
            self.last_activity_time = asyncio.get_event_loop().time()
            
            # Keep generating letter rows until we have enough valid words
            attempt_count = 0
            while len(self.score_words) < 35 and attempt_count < 10:
                self.create_letter_row()
                await self.create_score_words()
                attempt_count += 1
            
            if len(self.score_words) < 35:
                return False
                
            self.top_score_words = sorted(self.score_words, key=len, reverse=True)[:5]
            return True
        return False

    def end_clear(self):
        self.letter_row = []
        self.score_words = []
        self.found_words = []
        self.player_scores = {}
        self.top_score_words = []
        self.player_words = {}
        self.last_activity_time = None

    def ongoing_game_false(self):
        self.ongoing_game = False

    def sort_player_words(self):
        for player in self.player_words:
            self.player_words[player] = sorted(self.player_words[player], key=len, reverse=True)

    def update_activity_time(self):
        self.last_activity_time = asyncio.get_event_loop().time()

async def wordhunt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a new WordHunt game"""
    global wordhunt_games
    global activity_timers
    
    chat_id = update.effective_chat.id
    
    # Check if there's an active WordHunt game
    if chat_id in wordhunt_games and wordhunt_games[chat_id].ongoing_game:
        if context.args and context.args[0].lower() == 'force':
            await end_hunt(update, context)
        else:
            await update.message.reply_text("A WordHunt game is already in progress. Use /wordhunt force to start a new game.")
            return
    
    await update.message.reply_html("Generating Letters")
    
    # Create new game instance
    if chat_id not in wordhunt_games:
        wordhunt_games[chat_id] = WordHuntGame()
    
    if not await wordhunt_games[chat_id].start():
        await update.message.reply_text("Failed to start game. Please try again.")
        return

    # Cancel any existing timer and start a new one
    if chat_id in activity_timers and activity_timers[chat_id] is not None:
        activity_timers[chat_id].cancel()
    
    activity_timers[chat_id] = asyncio.create_task(check_activity(update, context, chat_id))
    
    await update.message.reply_html(upper_letters(wordhunt_games[chat_id].letter_row))

async def check_activity(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Check if there has been any activity in WordHunt in the last 30 seconds"""
    await asyncio.sleep(30)
    
    if chat_id not in wordhunt_games or not wordhunt_games[chat_id].ongoing_game:
        return
    
    current_time = asyncio.get_event_loop().time()
    if current_time - wordhunt_games[chat_id].last_activity_time > 30:
        await end_hunt(update, context)

async def handle_guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process a word submission for WordHunt"""
    chat_id = update.effective_chat.id
    if chat_id not in wordhunt_games or not wordhunt_games[chat_id].ongoing_game:
        return

    guess = update.message.text.strip().lower()
    player_name = update.effective_user.first_name or update.effective_user.username
    
    if len(guess) < 3:
        return
        
    game = wordhunt_games[chat_id]
    
    if guess in game.found_words:
        await update.message.reply_html(f"<b>{guess}</b> has already been found!")
        return
    
    if game.can_spell(guess) and guess.upper() in wordhunt_word_list:
        game.update_activity_time()
        score = len(guess) * len(guess)
        
        if guess.upper() in game.score_words:
            game.score_words.remove(guess.upper())
        game.found_words.append(guess)
        
        if player_name not in game.player_scores:
            game.player_scores[player_name] = 0
        if player_name not in game.player_words:
            game.player_words[player_name] = []
            
        game.player_words[player_name].append(guess)
        game.player_scores[player_name] += score
        
        await update_wordhunt_score(chat_id, player_name, score)
        
        notif = f"<i>{player_name}</i> found <b>{guess}</b> for {score} points!\n{upper_letters(game.letter_row)}"
        await update.message.reply_html(notif)
    else:
        await update.message.reply_html(f"<b>{guess}</b> is not a valid word!")

async def end_hunt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """End an active WordHunt game"""
    chat_id = update.effective_chat.id
    if chat_id not in wordhunt_games or not wordhunt_games[chat_id].ongoing_game:
        await update.message.reply_html("No active WordHunt game to end.")
        return
    
    wordhunt_games[chat_id].ongoing_game_false()
    await update.message.reply_html("<b>Game Ended!</b>")
    
    final_results = "🎉 SCORES: \n"
    for player, score in wordhunt_games[chat_id].player_scores.items():
        final_results += f"{player}: {score}\n"
    if not wordhunt_games[chat_id].player_scores:
        final_results = "No one played! \n"

    total_possible_words = len(wordhunt_games[chat_id].score_words) + len(wordhunt_games[chat_id].found_words)
    final_results += f"\n💡 BEST POSSIBLE WORDS ({total_possible_words} total): \n"
    for word in wordhunt_games[chat_id].top_score_words:
        final_results += word + "\n"
    
    wordhunt_games[chat_id].sort_player_words()
    final_results += "\n🔎 WORDS FOUND \n"
    for player in wordhunt_games[chat_id].player_words:
        final_results += f"<b>{player}({len(wordhunt_games[chat_id].player_words[player])})</b> \n"
        final_results += " ".join(wordhunt_games[chat_id].player_words[player]) + "\n"
    
    await update.message.reply_html(final_results)
    wordhunt_games[chat_id].end_clear()

    global activity_timers
    if chat_id in activity_timers:
        activity_timers[chat_id].cancel()
        del activity_timers[chat_id]

async def whleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display WordHunt leaderboard for current group"""
    chat_id = update.effective_chat.id
    top_players = list(wh_scores.find({"group_id": chat_id}).sort("score", -1).limit(10))
    
    if not top_players:
        await update.message.reply_text("No leaderboard data found for this group.")
        return

    reply = "🏆 <b>WordHunt Group Leaderboard</b> 🏆\n"
    for idx, player in enumerate(top_players, 1):
        reply += f"{idx}. {player['player_name']} - {player['score']} pts\n"
    
    await update.message.reply_html(reply)

async def whglobal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display global WordHunt leaderboard"""
    pipeline = [
        {"$group": {"_id": "$player_name", "score": {"$sum": "$score"}}},
        {"$sort": {"score": -1}},
        {"$limit": 10}
    ]
    top_players = list(wh_scores.aggregate(pipeline))

    if not top_players:
        await update.message.reply_text("No global leaderboard data found.")
        return

    reply = "🌍 <b>WordHunt Global Leaderboard</b> 🌍\n"
    for idx, player in enumerate(top_players, 1):
        reply += f"{idx}. {player['_id']} - {player['score']} pts\n"

    await update.message.reply_html(reply)

class ActiveWordHuntFilter(filters.MessageFilter):
    def filter(self, message):
        chat_id = message.chat_id
        return chat_id in wordhunt_games and wordhunt_games[chat_id].ongoing_game

active_wordhunt_filter = ActiveWordHuntFilter()

def register_handlers(application: Application) -> list:
    """Register all WordHunt handlers with the application"""
    handlers = [
        CommandHandler("wordhunt", wordhunt),
        CommandHandler("endhunt", end_hunt),
        CommandHandler("whleaderboard", whleaderboard),
        CommandHandler("whglobal", whglobal),
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS & active_wordhunt_filter,
            handle_guess,
            block=False
        )
    ]
    return handlers

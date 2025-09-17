from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pymongo import MongoClient
import requests
import logging
from urllib.parse import quote_plus
import os
from dotenv import load_dotenv  # For local dev only
from telegram import Bot


import time
load_dotenv()





# Enable logging (for debugging errors in bot)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

username = os.getenv("username")
password = os.getenv("password") # This will encode the '@' as '%40'


uri = f"mongodb+srv://{quote_plus(username)}:{quote_plus(password)}@cluster0.qerhys8.mongodb.net/"


# MongoDB Connection
client=MongoClient(uri)

db = client["leetcode_bot"]
users = db["users"]

# Fetch stats from LeetCode GraphQL API
def get_leetcode_stats(username: str) -> int:
    url = "https://leetcode.com/graphql"
    query = {
        "query": """
        query getUserProfile($username: String!) {
          matchedUser(username: $username) {
            submitStats {
              acSubmissionNum {
                difficulty
                count
              }
            }
          }
        }
        """,
        "variables": {"username": username},
    }

    try:
        res = requests.post(url, json=query, timeout=10).json()
        matched_user = res.get("data", {}).get("matchedUser")

        if not matched_user:
            return -1  # username not found

        ac_submissions = matched_user["submitStats"]["acSubmissionNum"]
        total = next((item["count"] for item in ac_submissions if item["difficulty"] == "All"), -1)
        return total
    except Exception as e:
        logger.error(f"Error fetching stats for {username}: {e}")
        return -1


# Register command
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("⚠️ Usage: /register <leetcode_username>")
        return

    username = context.args[0]
    solved = get_leetcode_stats(username)

    if solved == -1:
        await update.message.reply_text("❌ Invalid username or error fetching data.")
        return

    users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"leetcode_username": username, "total_solved": solved}},
        upsert=True,
    )

    await update.message.reply_text(f"✅ Registered *{username}* with {solved} problems solved!",
                                    parse_mode="Markdown")


# Leaderboard command - shows top 10 registered users
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_users = list(users.find().sort("total_solved", -1))
    if not all_users:
        await update.message.reply_text("No users registered yet.")
        return

    message = "🏆 *LeetCode Leaderboard* 🏆\n\n"

    rank = 1
    user_id = update.effective_user.id
    user_rank = None

    for user in all_users[:10]:  # Show top 10 users
        message += f"{rank}. *{user['leetcode_username']}* → {user['total_solved']} ✅\n"
        if user["telegram_id"] == user_id:
            user_rank = rank
        rank += 1

    if not user_rank:
        for idx, user in enumerate(all_users):
            if user["telegram_id"] == user_id:
                user_rank = idx + 1
                break

    if user_rank:
        message += f"\n🔎 Your Rank: {user_rank}/{len(all_users)}"

    await update.message.reply_text(message, parse_mode="Markdown")


# Single user search command - /search <leetcode_username>
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Usage: /search <leetcode_username>")
        return

    username = context.args[0]
    user = users.find_one({"leetcode_username": username})

    if not user:
        await update.message.reply_text(f"❌ User *{username}* not found in the database.", parse_mode="Markdown")
        return

    # Optionally refresh the stats
    solved = get_leetcode_stats(username)
    if solved != -1 and solved != user["total_solved"]:
        users.update_one({"leetcode_username": username}, {"$set": {"total_solved": solved}})
        message = f"🔄 Updated stats for *{username}*: {solved} problems solved! ✅"
    else:
        message = f"📊 *{username}*: {user['total_solved']} problems solved! ✅"

    await update.message.reply_text(message, parse_mode="Markdown")


def main():
    token = os.getenv("telegram_token")
    bot = Bot(token=token)
    app = Application.builder().bot(bot).build()

    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("search", search))

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":

    main()

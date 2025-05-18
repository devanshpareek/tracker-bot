from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import json
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, db

cred = credentials.Certificate("firebase_key.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://fitnesstracker-4cb44-default-rtdb.firebaseio.com'
})

# Replace with your actual token
BOT_TOKEN = "8039547756:AAFBameb2LIaoYHrnb0rI7ml-cr80UhHUF4"

# Default questions in case user doesn't set their own
DEFAULT_QUESTIONS = [
    "Did you complete your workout today? (Yes/No)",
    "Did you follow your diet today? (Yes/No)",
    "How much water did you drink (in liters)?",
    "How do you feel today? (Rate 1-5)"
]

# https://fitnesstracker-4cb44-default-rtdb.firebaseio.com

ASKING, OPTIONAL_NOTE_CONFIRM, OPTIONAL_NOTE_INPUT = range(3)


# Firebase references
def get_user_ref(user_id):
    return db.reference(f"/users/{user_id}")

def get_questions_ref(user_id):
    return db.reference(f"/user_questions/{user_id}")

# Command to set questions
# async def setquestions(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     user_id = str(update.effective_user.id)
#     text = update.message.text.partition(" ")[2]

#     if not text.strip():
#         await update.message.reply_text(
#             "Please send your questions separated by new lines after the command.\n\n"
#             "Example:\n/setquestions\nDid you work out?\nDid you drink water?"
#         )
#         return

#     questions = [q.strip() for q in text.split("\n") if q.strip()]
#     if not questions:
#         await update.message.reply_text("No valid questions found. Please try again.")
#         return

#     get_questions_ref(user_id).set(questions)
#     await update.message.reply_text(f"✅ Saved your {len(questions)} questions! Use /start to begin tracking.")


def load_data(path="/"):
    """Load data from a Firebase Realtime Database path."""
    ref = db.reference(path)
    data = ref.get()
    return data or {}

def save_data(path, data):
    """Save data to a Firebase Realtime Database path."""
    ref = db.reference(path)
    ref.set(data)


async def setquestions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    full_text = update.message.text

    # Remove the command part "/setquestions" from the full message text
    text_after_command = full_text[len("/setquestions"):].strip()

    if not text_after_command:
        await update.message.reply_text(
            "Please send your questions separated by new lines after the command.\n\n"
            "Example:\n/setquestions\nDid you work out?\nDid you drink water?"
        )
        return

    questions = [q.strip() for q in text_after_command.split("\n") if q.strip()]
    if not questions:
        await update.message.reply_text("No valid questions found. Please try again.")
        return

    # Save questions to Firebase or local storage
    data = load_data("/user_questions")
    data[user_id] = questions
    save_data("/user_questions", data)

    await update.message.reply_text(f"✅ Saved your {len(questions)} questions! Use /start to begin tracking.")



# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)

    # Fetch user's questions from Firebase
    questions_ref = db.reference(f"user_questions/{user_id}")
    questions = questions_ref.get() or DEFAULT_QUESTIONS

    context.user_data["questions"] = questions
    context.user_data["answers"] = {}
    context.user_data["q_index"] = 0

    # 🎉 Styled and colorful introduction
    intro_text = (
        "<b>👋 Welcome to your Daily Tracker!</b>\n\n"
        "Every day, I’ll ask you a few quick questions to help you stay consistent with your goals 💪.\n\n"
        "<b>✏️ You can customize your questions anytime using:</b>\n"
        "<code>/setquestions</code>\n"
        "Example:\n"
        "<code>/setquestions\nDid you exercise today?\nDid you drink 3L of water?\nDid you avoid junk food?</code>\n\n"
        "<b>📊 To view your progress:</b>\n"
        "<code>/history</code> or <code>/history 14</code> for 14 days\n\n"
        "Let's get started with your check-in for today 👇"
    )

    await update.message.reply_text(intro_text, parse_mode="HTML")

    # Start asking questions
    return await ask_questions(update, context)


# Ask questions
async def ask_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    q_index = context.user_data.get("q_index", 0)
    questions = context.user_data.get("questions", DEFAULT_QUESTIONS)

    if q_index > 0:
        context.user_data["answers"][str(q_index - 1)] = update.message.text.strip()

    if q_index == len(questions):
        context.user_data["q_index"] += 1
        await update.message.reply_text(
            "📝 <b>Would you like to leave a personal note for today?</b> (Yes/No)",
            parse_mode="HTML"
        )
        return OPTIONAL_NOTE_CONFIRM

    question_text = f"❓ <b>{questions[q_index]}</b>"
    await update.message.reply_text(question_text, parse_mode="HTML")
    context.user_data["q_index"] += 1
    return ASKING

# Confirm note
async def confirm_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text.strip().lower()
    if answer == "yes":
        await update.message.reply_text("Please type your message for today:")
        return OPTIONAL_NOTE_INPUT
    else:
        return await save_daily_data(update, context)

# Receive note
async def receive_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text.strip()
    context.user_data["answers"]["note"] = note
    return await save_daily_data(update, context)

# Save data to Firebase
async def save_daily_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    answers = context.user_data["answers"]

    get_user_ref(user_id).child(today).set(answers)
    await update.message.reply_text(
        "✅ <b>Your responses have been saved.</b> Great job staying consistent! 💪",
        parse_mode="HTML"
    )
    return ConversationHandler.END


# Cancel command
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Tracking canceled.")
    return ConversationHandler.END

# History command
async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    args = context.args

    user_data = get_user_ref(user_id).get()
    questions = get_questions_ref(user_id).get() or DEFAULT_QUESTIONS

    if not user_data:
        await update.message.reply_text("No history found.")
        return

    days = 7
    if args and args[0].isdigit():
        days = int(args[0])

    today = datetime.now().date()
    messages = [f"📅 <b>Your past {days} day(s):</b>\n"]
    yes_counters = [0] * len(questions)

    for i in range(days):
        date = str(today - timedelta(days=i))
        day_data = user_data.get(date)

        if day_data:
            messages.append(f"<u>{date}:</u>\n")
            for idx_str, answer in day_data.items():
                if idx_str == "note":
                    continue
                try:
                    idx = int(idx_str)
                except ValueError:
                    continue
                question = questions[idx] if idx < len(questions) else f"Q{idx+1}"
                answer_text = answer.strip().lower()
                emoji = "✅" if answer_text == "yes" else "❌"
                answer_styled = f"<b>{emoji} {answer.capitalize()}</b>"
                messages.append(f"❓ <b>{question}</b>\n➡️ {answer_styled}\n")
                if answer_text == "yes":
                    yes_counters[idx] += 1
            if "note" in day_data:
                messages.append(f"📝 <i>Note:</i> {day_data['note']}\n")
        else:
            messages.append(f"<u>{date}:</u>\nNo data\n")

    messages.append("\n📊 <b>Summary:</b>\n")
    for idx, question in enumerate(questions):
        messages.append(f"🔹 <b>{question}:</b> {yes_counters[idx]}/{days} yes")

    await update.message.reply_text("\n".join(messages), parse_mode="HTML")

# Main function
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASKING: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_questions)],
            OPTIONAL_NOTE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_note)],
            OPTIONAL_NOTE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_note)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("setquestions", setquestions))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("history", history))

    print("✅ Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()

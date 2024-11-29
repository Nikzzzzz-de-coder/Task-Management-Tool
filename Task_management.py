import telebot
from telebot.handler_backends import State, StatesGroup
from telebot.storage import StateMemoryStorage
import spacy
import parsedatetime
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List
from supabase import create_client, Client
import re
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Supabase client
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

# Initialize Telegram bot with state storage
state_storage = StateMemoryStorage()
bot = telebot.TeleBot(TELEGRAM_TOKEN, state_storage=state_storage)

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("Successfully connected to Supabase")
except Exception as e:
    print(f"Failed to initialize Supabase client: {str(e)}")
    raise

# Load spaCy model
try:
    nlp = spacy.load("en_core_web_md")
except OSError:
    print("Downloading spaCy model...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_md"])
    nlp = spacy.load("en_core_web_md")

# Define states for conversation handling
class BotStates(StatesGroup):
    waiting_for_task_choice = State()
    waiting_for_confirmation = State()

# Keep the existing TaskParser class and other helper functions...
# [Previous code remains the same until the interactive_query function]

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Handle /start and /help commands"""
    welcome_text = """
Hello! I'm your Task Management bot. Here's what you can do:

- Add tasks: "I need to complete project by tomorrow"
- View tasks: "Show all my tasks" or "What's due this week?"
- Complete tasks: "I've completed the python assignment"
- Delete tasks: "Delete math homework"

Try any of these commands or ask for help!
"""
    bot.reply_to(message, welcome_text)

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """Handle all incoming messages"""
    try:
        query = message.text.strip()
        chat_id = message.chat.id
        
        if is_completion_indicator(query):
            # Handle task completion/deletion
            handle_telegram_completion(message)
        elif query.lower().startswith('delete'):
            # Handle explicit deletion
            handle_telegram_deletion(message)
        elif any(indicator in query.lower() for indicator in TaskParser().task_indicators):
            # Handle task addition
            handle_telegram_task_addition(message)
        else:
            # Handle viewing queries
            results = handle_common_queries(query)
            if results:
                format_telegram_results(message, results)
            else:
                bot.reply_to(message, "No results to display.")
            
    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}\nPlease try again.")

def handle_telegram_completion(message):
    """Handle task completion for Telegram"""
    try:
        task_description = extract_task_description(message.text)
        if not task_description:
            bot.reply_to(message, "Please specify which task you completed.")
            return

        tasks = supabase.table("Task Data").select("*").execute().data
        if not tasks:
            bot.reply_to(message, "No tasks available.")
            return

        matching_tasks = find_matching_tasks(tasks, task_description)
        if not matching_tasks:
            available_tasks = "\n".join([f"- {task['Task_name']}" for task in tasks])
            bot.reply_to(message, 
                f"No tasks found matching '{task_description}'.\n\nAvailable tasks:\n{available_tasks}")
            return

        # Show matching tasks with inline keyboard
        markup = telebot.types.InlineKeyboardMarkup()
        for idx, task in enumerate(matching_tasks, 1):
            deadline = datetime.fromisoformat(task['Deadline'])
            button_text = f"{task['Task_name']} (due {deadline.strftime('%Y-%m-%d')})"
            callback_data = f"complete_{task['id']}"
            markup.add(telebot.types.InlineKeyboardButton(button_text, callback_data=callback_data))

        bot.reply_to(message, "Which task did you complete?", reply_markup=markup)
        
    except Exception as e:
        bot.reply_to(message, f"Error handling task completion: {str(e)}")

def handle_telegram_deletion(message):
    """Handle task deletion for Telegram"""
    try:
        task_description = message.text.lower().replace('delete', '', 1).strip()
        if not task_description:
            bot.reply_to(message, "Please specify what task you want to delete.")
            return

        tasks = supabase.table("Task Data").select("*").execute().data
        matching_tasks = find_matching_tasks(tasks, task_description)

        if not matching_tasks:
            available_tasks = "\n".join([f"- {task['Task_name']}" for task in tasks])
            bot.reply_to(message, 
                f"No tasks found matching '{task_description}'.\n\nAvailable tasks:\n{available_tasks}")
            return

        # Create inline keyboard for task selection
        markup = telebot.types.InlineKeyboardMarkup()
        for idx, task in enumerate(matching_tasks, 1):
            deadline = datetime.fromisoformat(task['Deadline'])
            button_text = f"{task['Task_name']} (due {deadline.strftime('%Y-%m-%d')})"
            callback_data = f"delete_{task['id']}"
            markup.add(telebot.types.InlineKeyboardButton(button_text, callback_data=callback_data))

        bot.reply_to(message, "Which task would you like to delete?", reply_markup=markup)

    except Exception as e:
        bot.reply_to(message, f"Error handling deletion: {str(e)}")

def handle_telegram_task_addition(message):
    """Handle task addition for Telegram"""
    try:
        parser = TaskParser()
        task_details = parser.extract_task_details(message.text)
        
        if task_details:
            response = supabase.table("Task Data").insert(task_details).execute()
            if response.data:
                # Convert deadline to a more readable format
                deadline = datetime.fromisoformat(task_details['Deadline'])
                deadline_str = deadline.strftime("%I:%M %p on %B %d")  # e.g., "3:30 PM on November 30"
                
                # List of random confirmation messages
                confirmations = [
                    f"Got it! I've added *{task_details['Task_name']}* to your list.",
                    f"Alright, I'll remind you about *{task_details['Task_name']}*.",
                    f"Added *{task_details['Task_name']}* to your tasks!",
                    f"No problem! *{task_details['Task_name']}* is on your list.",
                    f"Sure thing! I've noted down *{task_details['Task_name']}*."
                ]
                
                # List of random deadline phrases
                deadline_phrases = [
                    f"You'll need to finish this by {deadline_str}.",
                    f"Make sure to complete it by {deadline_str}.",
                    f"The deadline is {deadline_str}.",
                    f"Try to get this done before {deadline_str}.",
                    f"You have until {deadline_str} for this one."
                ]
                
                # List of random difficulty acknowledgments
                difficulty_phrases = {
                    'Easy': [
                        "Should be pretty straightforward! 👍",
                        "This looks manageable! 😊",
                        "You'll handle this easily! ✨"
                    ],
                    'Medium': [
                        "You've got this! 💪",
                        "A good challenge ahead! 🎯",
                        "Take it step by step! 📈"
                    ],
                    'Hard': [
                        "A challenging one, but I believe in you! 💪",
                        "Take your time with this one! 🎯",
                        "Break it down into smaller tasks if needed! 📊"
                    ]
                }
                
                # Randomly select messages from each category
                import random
                confirmation = random.choice(confirmations)
                deadline_phrase = random.choice(deadline_phrases)
                difficulty_phrase = random.choice(difficulty_phrases[task_details['difficulty']])
                
                # Combine the messages naturally
                reply = f"{confirmation} {deadline_phrase} {difficulty_phrase}"
                
                bot.reply_to(message, reply, parse_mode='Markdown')
            else:
                bot.reply_to(message, "Sorry, I couldn't add that task. Could you try saying that again?")
        else:
            bot.reply_to(message, "I didn't quite catch that. Could you tell me the task and when it's due?")
    
    except Exception as e:
        bot.reply_to(message, "Oops, something went wrong! Could you try saying that in a different way?")

def format_telegram_results(message, tasks: List[Dict[str, Any]]):
    """Format and send task results for Telegram"""
    if not tasks:
        bot.reply_to(message, "No tasks found.")
        return

    sorted_tasks = sorted(tasks, key=lambda x: datetime.fromisoformat(x['Deadline']))
    current_date = datetime.now()

    result_text = "*Your Tasks:*\n\n"
    for task in sorted_tasks:
        deadline = datetime.fromisoformat(task['Deadline'])
        days_until = (deadline.date() - current_date.date()).days

        if days_until < 0:
            days_str = f"{abs(days_until)} days overdue"
        elif days_until == 0:
            days_str = "Due today"
        else:
            days_str = f"{days_until} day{'s' if days_until > 1 else ''} left"

        status = task.get('Status', 'To Do')
        
        result_text += (f"• *{task['Task_name']}*\n"
                       f"  Due: {deadline.strftime('%Y-%m-%d %H:%M')}\n"
                       f"  Difficulty: {task['difficulty']}\n"
                       f"  Status: {status}\n"
                       f"  {days_str}\n\n")

    # Split long messages if needed (Telegram has a 4096 character limit)
    if len(result_text) > 4000:
        chunks = [result_text[i:i+4000] for i in range(0, len(result_text), 4000)]
        for chunk in chunks:
            bot.reply_to(message, chunk, parse_mode='Markdown')
    else:
        bot.reply_to(message, result_text, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith(('complete_', 'delete_')))
def handle_task_callback(call):
    """Handle callback queries from inline keyboards"""
    try:
        action, task_id = call.data.split('_')
        task_response = supabase.table("Task Data").select("*").eq("id", task_id).execute()
        
        if not task_response.data:
            bot.answer_callback_query(call.id, "Task not found!")
            return

        task = task_response.data[0]
        
        if action == 'complete':
            # Delete the completed task
            supabase.table("Task Data").delete().eq("id", task_id).execute()
            bot.answer_callback_query(call.id, f"Great job! Task '{task['Task_name']}' completed!")
            bot.edit_message_text(
                f"Task '*{task['Task_name']}*' marked as completed and removed from your list! 🎉",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown'
            )
        
        elif action == 'delete':
            # Delete the task
            supabase.table("Task Data").delete().eq("id", task_id).execute()
            bot.answer_callback_query(call.id, f"Task '{task['Task_name']}' deleted!")
            bot.edit_message_text(
                f"Task '*{task['Task_name']}*' has been deleted.",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown'
            )

    except Exception as e:
        bot.answer_callback_query(call.id, f"Error: {str(e)}")

def main():
    """Main function to run the bot"""
    print("Starting bot...")
    bot.infinity_polling()

if __name__ == "__main__":
    main()

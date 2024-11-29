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
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("Downloading spaCy model...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
    nlp = spacy.load("en_core_web_sm")

# Define states for conversation handling
class BotStates(StatesGroup):
    waiting_for_task_choice = State()
    waiting_for_confirmation = State()

# Helper Functions
def is_completion_indicator(text: str) -> bool:
    """Check if the message indicates task completion."""
    completion_phrases = [
        'completed',
        'done',
        'finished',
        'complete',
        'did',
        'accomplished',
        'achieved',
        'concluded'
    ]
    text = text.lower()
    return any(phrase in text for phrase in completion_phrases)

def extract_task_description(text: str) -> str:
    """Extract task description from completion message."""
    completion_phrases = [
        'completed',
        'done',
        'finished',
        'complete',
        'did',
        'accomplished',
        'achieved',
        'concluded'
    ]
    text = text.lower()
    for phrase in completion_phrases:
        text = text.replace(phrase, '')
    return text.strip()

def find_matching_tasks(tasks: List[Dict[str, Any]], description: str) -> List[Dict[str, Any]]:
    """Find tasks that match the given description."""
    description = description.lower()
    return [
        task for task in tasks
        if description in task['Task_name'].lower()
    ]

def handle_common_queries(query: str) -> List[Dict[str, Any]]:
    """Handle common task queries"""
    try:
        # Get all tasks from database
        tasks = supabase.table("Task Data").select("*").execute().data
        
        query = query.lower()
        current_date = datetime.now()
        
        # Filter tasks based on query
        if 'due today' in query or "today's tasks" in query:
            return [
                task for task in tasks
                if datetime.fromisoformat(task['Deadline']).date() == current_date.date()
            ]
            
        elif 'due this week' in query or 'this week' in query:
            week_end = current_date + timedelta(days=7)
            return [
                task for task in tasks
                if current_date.date() <= datetime.fromisoformat(task['Deadline']).date() <= week_end.date()
            ]
            
        elif 'all' in query or 'list' in query:
            return tasks
            
        elif 'overdue' in query:
            return [
                task for task in tasks
                if datetime.fromisoformat(task['Deadline']).date() < current_date.date()
            ]
            
        return tasks  # Default to showing all tasks
        
    except Exception as e:
        print(f"Error handling query: {str(e)}")
        return []

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

# TaskParser Class
class TaskParser:
    """Class to parse task details from user messages."""
    
    def __init__(self):
        self.cal = parsedatetime.Calendar()
        self.task_indicators = [
            'need to',
            'have to',
            'must',
            'should',
            'want to',
            'going to',
            'gotta',
            'got to',
            'due'
        ]

    def extract_task_details(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract task name and deadline from text."""
        try:
            # Extract deadline
            time_struct, parse_status = self.cal.parse(text)
            if parse_status == 0:
                return None
            
            deadline = datetime(*time_struct[:6])
            
            # Extract task name
            doc = nlp(text)
            task_name = None
            
            # Look for task indicators
            for indicator in self.task_indicators:
                if indicator in text.lower():
                    # Split by indicator and take the latter part
                    parts = text.lower().split(indicator, 1)
                    if len(parts) > 1:
                        task_text = parts[1]
                        # Clean up the task text
                        task_name = task_text.split('by')[0].strip()
                        task_name = task_name.split('until')[0].strip()
                        task_name = task_name.split('before')[0].strip()
                        break
            
            if not task_name:
                return None
                
            # Determine difficulty based on text analysis
            difficulty = self.determine_difficulty(text)
            
            return {
                'Task_name': task_name.capitalize(),
                'Deadline': deadline.isoformat(),
                'Status': 'To Do',
                'difficulty': difficulty
            }
            
        except Exception as e:
            print(f"Error parsing task: {str(e)}")
            return None

    def determine_difficulty(self, text: str) -> str:
        """Determine task difficulty based on text analysis."""
        # Keywords indicating difficulty
        difficulty_indicators = {
            'Easy': ['simple', 'easy', 'quick', 'basic'],
            'Hard': ['difficult', 'hard', 'complex', 'challenging'],
            'Medium': ['moderate', 'medium']
        }
        
        text = text.lower()
        
        # Check for explicit difficulty indicators
        for difficulty, indicators in difficulty_indicators.items():
            if any(indicator in text for indicator in indicators):
                return difficulty
        
        # Default to Medium if no indicators found
        return 'Medium'

# Existing TaskParser Related Code
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

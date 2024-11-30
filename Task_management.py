import random
import re
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from supabase import create_client, Client
import nest_asyncio
import asyncio
import os
from dotenv import load_dotenv
import spacy
import parsedatetime
from typing import Optional, Dict, Any, Tuple, List
import re
import calendar

# Load environment variables
load_dotenv()

# Initialize Supabase client
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
print("Successfully connected to Supabase")

def is_completion_indicator(text: str) -> bool:
    """Check if the message indicates task completion"""
    completion_indicators = [
        r"i have completed\s+", r"i've completed\s+", r"i have done\s+",
        r"i've done\s+", r"i finished\s+", r"i've finished\s+",
        r"i completed\s+", r"i've accomplished\s+", r"i accomplished\s+",
        r"i got it done\s+", r"i've got it done\s+", r"i managed to\s+",
        r"i've managed to\s+", r"i did\s+", r"i've handled\s+",
        r"i handled\s+", r"i wrapped up\s+", r"i've wrapped up\s+",
        r"is done$", r"is completed$", r"is finished$",
        r"done$", r"completed$"
    ]
    return any(re.search(pattern, text.lower()) for pattern in completion_indicators)

class TaskParser:
    def __init__(self):
        self.cal = parsedatetime.Calendar()
        self.task_verbs = [
            'do', 'complete', 'finish', 'submit', 'work',
            'prepare', 'review', 'add', 'create'
        ]
        self.task_nouns = [
            'task', 'assignment', 'project', 'homework',
            'work', 'deadline', 'due', 'chapter'
        ]

        # Task intention indicators
        self.task_indicators = [
            # First person indicators
            'i gotta', 'i have to', 'i need to', 'i must', 'i should',
            'i ought to', 'i will', 'i wanna', 'i plan to', 'i intend to',
            "i'm going to", "i'll", "i'd like to",

            # Shortened versions
            'gotta', 'need to', 'have to', 'should', 'must', 'ought to',
            'will', 'wanna', 'plan to', 'intend to', 'gonna', 'needa',
            'haveta', 'shoulda', 'oughta', 'will do',

            # Task-specific indicators
            'to do', 'to complete'
        ]

        # Temporal relations for deadlines
        self.temporal_relations = {
            'before': [
                'before', 'by', 'prior to', 'earlier than', 'up until',
                'before the end of', 'before the deadline', 'not later than',
                'before the specified date', 'till', 'until', 'no later than'
            ],
            'inclusive': [
                'on', 'including',
            ],
            'after': [
                'after', 'following', 'post', 'from', 'beyond',
                'later than', 'after the deadline', 'subsequent to',
                'onwards', 'onward', 'starting from'
            ],
            'flexible': [
                'around', 'about', 'within the week', 'within the month',
                'sometime', 'whenever', 'at the earliest', 'as soon as',
                'in the near future', 'approximately', 'roughly'
            ]
        }

        # Relative time patterns
        self.relative_patterns = {
            'this_week': r'this week',
            'next_week': r'next week',
            'this_month': r'this month',
            'next_month': r'next month',
            'today': r'today',
            'tomorrow': r'tomorrow',
            'weekend': r'(this |)weekend'
        }

        # Specific day patterns
        self.specific_days = {
            'sunday': r'(this |next |)sunday',
            'monday': r'(this |next |)monday',
            'tuesday': r'(this |next |)tuesday',
            'wednesday': r'(this |next |)wednesday',
            'thursday': r'(this |next |)thursday',
            'friday': r'(this |next |)friday',
            'saturday': r'(this |next |)saturday'
        }

    def parse_task(self, text: str) -> dict:
        # Your existing parse_task implementation
        pass

def add_task_natural(text: str) -> dict:
    parser = TaskParser()
    task_data = parser.parse_task(text)
    if task_data:
        result = supabase.table("Task Data").insert(task_data).execute()
        return result.data[0] if result.data else None
    return None

def handle_common_queries(query: str) -> list:
    """Handle various task-related queries"""
    query_lower = query.lower()
    
    # Get all tasks
    tasks = supabase.table("Task Data").select("*").execute().data
    
    if not tasks:
        return []
        
    if any(phrase in query_lower for phrase in ['show', 'list', 'what', 'display']):
        return tasks
        
    # Add other query handling as needed
    return []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    welcome_message = """
Hey there! I'm your personal task buddy!

I can help you keep track of everything you need to do. Just chat with me naturally like:
• "Need to finish the project by tomorrow"
• "Remind me to study for math test next week"
• "I've completed the python assignment"

Just tell me what's on your plate, and I'll help you stay organized! 😊
"""
    await update.message.reply_text(welcome_message)

def format_telegram_results(tasks):
    """Format task results for Telegram display"""
    if not tasks:
        return "Looks like your schedule is clear! 🎉"

    sorted_tasks = sorted(tasks, key=lambda x: datetime.fromisoformat(x['Deadline']))
    current_date = datetime.now()
    
    response = "Here's what you've got on your plate:\n\n"
    for task in sorted_tasks:
        deadline = datetime.fromisoformat(task['Deadline'])
        days_until = (deadline.date() - current_date.date()).days
        
        if days_until < 0:
            days_str = f"⚠️ Yikes! This is {abs(days_until)} days overdue"
        elif days_until == 0:
            days_str = "⏰ This is due today!"
        elif days_until == 1:
            days_str = "📅 Due tomorrow!"
        else:
            days_str = f"✅ You've got {days_until} days to nail this"
            
        response += f"• {task['Task_name']}\n"
        response += f"  Due: {deadline.strftime('%Y-%m-%d %H:%M')}\n"
        if task['difficulty'] == 'Hard':
            response += f"  This one's a bit challenging 💪\n"
        elif task['difficulty'] == 'Medium':
            response += f"  Moderate effort needed 🎯\n"
        else:
            response += f"  Should be pretty straightforward ✨\n"
        response += f"  {days_str}\n\n"
    
    return response

async def handle_task_completion(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
    """Handle task completion/deletion based on various completion phrases"""
    try:
        # Remove completion indicators to get task description
        task_description = query.lower()
        for pattern in [
            r"i have completed\s+", r"i've completed\s+", r"i have done\s+",
            r"i've done\s+", r"i finished\s+", r"i've finished\s+",
            r"i completed\s+", r"i've accomplished\s+", r"i accomplished\s+",
            r"i got it done\s+", r"i've got it done\s+", r"i managed to\s+",
            r"i've managed to\s+", r"i did\s+", r"i've handled\s+",
            r"i handled\s+", r"i wrapped up\s+", r"i've wrapped up\s+",
            r"is done$", r"is completed$", r"is finished$",
            r"done$", r"completed$"
        ]:
            task_description = re.sub(pattern, "", task_description, flags=re.IGNORECASE)

        # Get all tasks from the database
        tasks = supabase.table("Task Data").select("*").execute().data
        if not tasks:
            await update.message.reply_text("No tasks available.")
            return

        # Find matching tasks based on partial name match
        matching_tasks = []
        for task in tasks:
            if any(term in task['Task_name'].lower() for term in task_description.split()):
                matching_tasks.append(task)

        if not matching_tasks:
            await update.message.reply_text(f"No tasks found matching '{task_description}'.")
            return

        # If there's exactly one match, complete it directly
        if len(matching_tasks) == 1:
            task_to_delete = matching_tasks[0]
            supabase.table("Task Data").delete().eq("id", task_to_delete['id']).execute()
            completion_responses = [
                f"🎉 Awesome job finishing '{task_to_delete['Task_name']}'! One less thing to worry about!",
                f"💪 Nice work! '{task_to_delete['Task_name']}' is done and dusted!",
                f"✨ You crushed it! '{task_to_delete['Task_name']}' is complete!",
                f"🌟 Great going! '{task_to_delete['Task_name']}' is checked off your list!",
                f"🚀 Look at you go! '{task_to_delete['Task_name']}' is finished!"
            ]
            await update.message.reply_text(random.choice(completion_responses))
            return

        # If there are multiple matches, show them as a numbered list with inline keyboard
        task_list = "I found a few tasks that could match. Which one did you complete?\n\n"
        for idx, task in enumerate(matching_tasks, 1):
            deadline = datetime.fromisoformat(task['Deadline'])
            task_list += f"{idx}. {task['Task_name']} (due {deadline.strftime('%Y-%m-%d %H:%M')})\n"
        
        task_list += "\nJust send me the number! 😊"
        await update.message.reply_text(task_list)
        
        # Store the matching tasks in the context for later use
        context.user_data['pending_completion'] = matching_tasks

    except Exception as e:
        await update.message.reply_text(f"Error handling task completion: {str(e)}")

def is_greeting(text: str) -> bool:
    """Check if the message is a greeting"""
    greeting_phrases = {
        # Basic greetings
        'hi', 'hello', 'hey', 'yo', 'hola', 'howdy', 'sup', 
        'greetings', 'good morning', 'good afternoon', 'good evening',
        
        # Casual greetings
        'heya', 'hiya', 'hi there', 'hello there', 'hey there',
        'what\'s up', 'whats up', 'wassup', 'what up', 'sup',
        
        # How are you variants
        'how are you', 'how\'s it going', 'how you doing',
        'how r u', 'how are u', 'how r you',
        
        # Time-based
        'morning', 'afternoon', 'evening', 'night',
        
        # Informal
        'yo yo', 'heyo', 'heyy', 'hii', 'hihi', 'hola',
        'aloha', 'bonjour', 'ciao'
    }
    
    text_lower = text.lower().strip()
    
    # Check for exact matches
    if any(text_lower == phrase for phrase in greeting_phrases):
        return True
    
    # Check for partial matches at the start of the message
    return any(text_lower.startswith(phrase) for phrase in greeting_phrases)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages."""
    query = update.message.text.strip()
    
    try:
        # Check for greetings first
        if is_greeting(query):
            greeting_responses = [
                "Hey there! 👋 How can I help you with your tasks today?",
                "Hello! 😊 Ready to help you stay organized!",
                "Hi! Need help managing your tasks?",
                "Hey! 🌟 What can I do for you today?",
                "Hello there! Ready to tackle some tasks?",
                "Hi! 🎯 Let me know what you need help with!",
                "Hey! Looking to add or check your tasks?",
                "Hello! 📝 How can I assist you today?",
                "Hi there! Ready to help you stay productive! ✨",
                "Hey! Let's get those tasks organized! 🚀"
            ]
            await update.message.reply_text(random.choice(greeting_responses))
            return
            
        # Check if it's a task query
        if any(phrase in query.lower() for phrase in [
            'what tasks', 'show tasks', 'list tasks', 'pending tasks',
            'due tasks', 'tasks due', 'what is due', 'what\'s due'
        ]):
            results = handle_common_queries(query)
            if results:
                response = format_telegram_results(results)
                await update.message.reply_text(response)
            else:
                await update.message.reply_text("No tasks found for your query! 🎉")
            return
            
        # Then check for farewells
        if is_farewell(query):
            farewell_responses = [
                "Catch you later! Don't forget about those tasks! 👋",
                "Take it easy! I'll be here when you need me again! 😊",
                "Alright, catch you on the flip side! Keep crushing those tasks! ✨",
                "See ya! Remember, you've got this! 🌟",
                "Later! Don't let those deadlines sneak up on you! ⏰",
                "You're doing great! Come back anytime you need help! 🎯",
                "Peace out! Keep that productivity flowing! 🚀",
                "Take care! Your tasks will be waiting right here! 📝",
                "Until next time! Stay awesome and organized! ⭐",
                "Bye for now! Keep up the great work! 🎮"
            ]
            await update.message.reply_text(random.choice(farewell_responses))
            return

        # Check if this is a response to a pending task completion
        if 'pending_completion' in context.user_data and query.isdigit():
            choice_num = int(query)
            matching_tasks = context.user_data['pending_completion']
            
            if 1 <= choice_num <= len(matching_tasks):
                task_to_delete = matching_tasks[choice_num - 1]
                supabase.table("Task Data").delete().eq("id", task_to_delete['id']).execute()
                await update.message.reply_text(
                    f"Great job! Task '**{task_to_delete['Task_name']}**' has been marked as completed and removed from your list."
                )
                # Clear the pending completion
                del context.user_data['pending_completion']
                return
            else:
                await update.message.reply_text("Invalid number. Please try again.")
                return
                
        if is_completion_indicator(query):
            # Handle task completion/deletion - pass context parameter
            await handle_task_completion(update, context, query)
        elif any(indicator in query.lower() for indicator in TaskParser().task_indicators) or \
             query.lower().startswith('add'):
            # Handle task addition
            added_task = add_task_natural(query)
            response = f"Task added: {added_task['Task_name'] if added_task else 'Failed to add task'}"
            await update.message.reply_text(response)
        elif query.lower().startswith('delete'):
            # Handle explicit deletion
            delete_task(query)
            await update.message.reply_text("Task deletion processed.")
        else:
            # Handle other queries
            results = handle_common_queries(query)
            if results:
                # Format results for Telegram
                response = format_telegram_results(results)
            else:
                response = "No results to display."
            await update.message.reply_text(response)
        
    except Exception as e:
        error_message = f"Error processing your request: {str(e)}"
        await update.message.reply_text(error_message)

def is_farewell(text: str) -> bool:
    """Check if the message is a farewell or casual acknowledgment"""
    # First check if it's a task query
    task_queries = [
        'what tasks', 'show tasks', 'list tasks', 'pending tasks',
        'due tasks', 'tasks due', 'what is due', 'what\'s due'
    ]
    
    text_lower = text.lower().strip()
    
    # If it's a task query, it's not a farewell
    if any(query in text_lower for query in task_queries):
        return False
    
    farewell_phrases = {
        # Original farewells
        'bye', 'goodbye', 'see you', 'cool', 'ok', 'okay', 'cya', 
        'later', 'take care', 'ttyl', 'gtg', 'got to go', 
        'have to go', 'catch you later', 'peace out',
        
        # Additional casual acknowledgments
        'alright', 'aight', 'good to go', "let's go", 'lesgo', 
        'lessgo', 'lessgoo', 'lessgooo', 'lets go', 
        'sounds good', 'perfect', 'great', 'awesome',
        'nice', 'got it', 'understood', 'roger that',
        'will do', 'noted', 'right on',
        
        # Follow-up responses
        'yeah', 'yep', 'yup', 'yes', 'sure', 'k', 
        'kk', 'mhm', 'uh huh', 'right', 'yea', 'yea boi'
    }
    
    # Check for exact matches first
    if any(text_lower == phrase for phrase in farewell_phrases):
        return True
    
    # Check for partial matches within words
    words = text_lower.split()
    return any(
        any(phrase in word for word in words)
        for phrase in farewell_phrases
    ) and not any(query in text_lower for query in task_queries)

if __name__ == "__main__":
    try:
        # Create the Application and pass it your bot's token
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # Start the bot
        print("Starting bot...")
        application.run_polling()
        
    except Exception as e:
        print(f"Error starting bot: {str(e)}")

import logging
from telegram import Update, ForceReply
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from Task_management import (
    handle_common_queries,
    add_task_natural,
    view_tasks,
    edit_task,
    delete_task,
    mark_task_completed,
    is_completion_indicator,
    handle_task_completion,
    interactive_query,
)

import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def start(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    update.message.reply_markdown_v2(
        fr'Hi {user.mention_markdown_v2()}\! I can help you manage your tasks\. You can add, view, edit, or delete tasks.\n\nFor example:\n- Add task: "I need to complete the report by tomorrow"\n- View tasks: "Show all my tasks"\n- Complete task: "I have completed the report"',
        reply_markup=ForceReply(selective=True),
    )

def help_command(update: Update, context: CallbackContext) -> None:
    """Send a message when the command /help is issued."""
    help_text = (
        "Here are the commands you can use:\n\n"
        "/add <task_description> - Add a new task.\n"
        "/view - View all your tasks.\n"
        "/edit <task_id> - Edit a task.\n"
        "/delete <task_id> - Delete a task.\n"
        "/complete <task_id> - Mark a task as completed.\n"
        "\nYou can also send natural language queries like:\n"
        "- 'I need to complete the report by tomorrow'\n"
        "- 'Show all my tasks'\n"
        "- 'I have completed the report'"
    )
    update.message.reply_text(help_text)

def handle_message(update: Update, context: CallbackContext) -> None:
    """Handle incoming messages and process them as queries."""
    text = update.message.text
    if is_completion_indicator(text):
        handle_task_completion(text)
        update.message.reply_text("Task completion processed.")
    elif any(indicator in text.lower() for indicator in TaskParser().task_indicators) or text.lower().startswith('add'):
        added_task = add_task_natural(text)
        if added_task:
            update.message.reply_text(f"Task '{added_task['Task_name']}' added successfully!")
        else:
            update.message.reply_text("Failed to add task. Please check your input.")
    elif text.lower().startswith('delete'):
        delete_task(text)
        update.message.reply_text("Task deleted successfully.")
    else:
        results = handle_common_queries(text)
        if results:
            formatted = format_task_results(results)
            update.message.reply_text(formatted)
        else:
            update.message.reply_text("No results to display.")

def main():
    """Start the bot."""
    updater = Updater(TELEGRAM_BOT_TOKEN)

    dispatcher = updater.dispatcher

    # Register handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    # Start the Bot
    updater.start_polling()

    logger.info("Bot started. Listening for messages...")

    # Run the bot until you press Ctrl-C
    updater.idle()

if __name__ == '__main__':
    main()

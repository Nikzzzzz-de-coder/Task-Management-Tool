# Task Management Tool 🗓️

A Telegram bot powered by Natural Language Processing that helps users manage their tasks efficiently. The bot understands natural language commands, making task management intuitive and user-friendly.

## Features ✨

- **Natural Language Processing**: Add tasks using everyday language
- **Smart Deadline Detection**: Automatically understands various date/time formats
- **Task Management**:
  - Add new tasks with deadlines
  - View all tasks and their status
  - Mark tasks as complete
  - Delete tasks
- **Difficulty Levels**: Automatically assigns task difficulty (Easy/Medium/Hard)
- **Interactive Interface**: Uses Telegram's inline keyboards for better user experience

## Tech Stack 🛠️

- Python 3.7+
- Telegram Bot API
- Supabase (Database)
- spaCy (NLP)
- parsedatetime (Date parsing)

## Setup 🚀

1. **Clone the repository**

   ```bash
   git clone https://github.com/Nikzzzzz-de-coder/Task-Management-Tool.git
   cd Task-Management-Tool
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   python -m spacy download en_core_web_sm
   ```

3. **Environment Setup**

   - Create a `.env` file in the root directory
   - Add your credentials:
     ```
     TELEGRAM_TOKEN=your_telegram_bot_token
     SUPABASE_URL=your_supabase_url
     SUPABASE_KEY=your_supabase_key
     ```

4. **Run the bot**
   ```bash
   python Task_management.py
   ```

## Usage 📝

Start a chat with the bot on Telegram and try these commands:

- "I need to finish the report by tomorrow at 5pm"
- "Show me all my tasks"
- "What's due this week?"
- "I've completed the python assignment"
- "Delete math homework"

## Commands 🎯

- `/start` - Initialize the bot
- `/help` - Get usage instructions

## Contributing 🤝

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License 📄

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments 🙏

- Telegram Bot API
- Supabase Team
- spaCy Natural Language Processing

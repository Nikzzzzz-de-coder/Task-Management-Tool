import spacy
import parsedatetime
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List
from supabase import create_client, Client
import re
import calendar
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("Successfully connected to Supabase")
except Exception as e:
    print(f"Failed to initialize Supabase client: {str(e)}")
    raise

# Load spaCy model
try:
    nlp = spacy.load("en_core_web_sm")  # Ensure you've downloaded this model
except OSError:
    print("Downloading 'en_core_web_sm' model for spaCy as it was not found...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
    nlp = spacy.load("en_core_web_sm")

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
        
        # Expanded temporal relations
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
        
        # Add relative time patterns
        self.relative_patterns = {
            'this_week': r'this week',
            'next_week': r'next week',
            'this_month': r'this month',
            'next_month': r'next month',
            'today': r'today',
            'tomorrow': r'tomorrow',
            'weekend': r'(this |)weekend'
        }

        # Add specific day patterns
        self.specific_days = {
            'sunday': r'(this |next |)sunday',
            'monday': r'(this |next |)monday',
            'tuesday': r'(this |next |)tuesday',
            'wednesday': r'(this |next |)wednesday',
            'thursday': r'(this |next |)thursday',
            'friday': r'(this |next |)friday',
            'saturday': r'(this |next |)saturday'
        }

        # Add task intention indicators
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

    def is_task_query(self, doc) -> bool:
        """Check if the query is task-related"""
        text = doc.text.lower()
        
        # Check for task indicators
        if any(indicator in text for indicator in self.task_indicators):
            return True
            
        # Check existing task verbs and nouns
        return any(verb in text for verb in self.task_verbs) or \
               any(noun in text for noun in self.task_nouns)

    def extract_task_details(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract task details from natural language input"""
        task_name = self._extract_task_name(nlp(text.lower()), text)
        deadline = self._extract_deadline(nlp(text.lower()), text)
        difficulty = self._extract_difficulty(text)
        
        if task_name and deadline:
            return {
                'Task_name': task_name,
                'Deadline': deadline.strftime("%Y-%m-%dT%H:%M:%S"),
                'difficulty': difficulty,
                'Status': 'To Do'  # Set default status to "To Do"
            }
        return None

    def _extract_task_name(self, doc, text: str) -> Optional[str]:
        """Extract the task name using dependency parsing"""
        # Words to remove from the beginning of task names
        remove_words = [
            'also', 'even', 'as well', 'additionally', 'moreover',
            'furthermore', 'besides', 'too'
        ]
        
        task_name = None
        
        # Try to find task name after task indicators
        for indicator in self.task_indicators:
            if indicator in text.lower():
                # Split text after the indicator
                parts = text.lower().split(indicator, 1)
                if len(parts) > 1:
                    # Get the part after the indicator but before any deadline words
                    potential_name = parts[1].strip()
                    for deadline_word in ['by', 'due', 'until', 'before']:
                        if deadline_word in potential_name:
                            potential_name = potential_name.split(deadline_word)[0].strip()
                    
                    # Remove the words we want to filter out
                    for word in remove_words:
                        if potential_name.startswith(word):
                            potential_name = potential_name.replace(word, '', 1).strip()
                    
                    if potential_name:
                        task_name = potential_name.capitalize()
                        break
        
        # If no task name found through indicators, try dependency parsing
        if not task_name:
            for token in doc:
                if token.dep_ == 'dobj' or (token.dep_ == 'pobj' and token.head.dep_ == 'prep'):
                    task_name = ' '.join([t.text for t in token.subtree]).strip()
                    
                    # Remove the words we want to filter out
                    for word in remove_words:
                        if task_name.lower().startswith(word):
                            task_name = task_name.replace(word, '', 1).strip()
                    
                    task_name = task_name.capitalize()
                    break
        
        return task_name

    def _extract_deadline(self, doc, text: str) -> Optional[datetime]:
        """Extract the deadline from the input text"""
        # Look for prepositions indicating deadline
        for token in doc:
            if token.text in ['by', 'due', 'until']:
                # The object of the preposition is likely the deadline
                for child in token.children:
                    if child.dep_ in ['pobj', 'nmod']:
                        deadline_text = ' '.join([t.text for t in child.subtree])
                        deadline = self.parse_deadline(deadline_text)
                        if deadline:
                            return deadline
        
        # Fallback using regex
        deadline_match = re.search(r'(due|by)\s+(.+)', text, re.IGNORECASE)
        if deadline_match:
            deadline_text = deadline_match.group(2)
            deadline = self.parse_deadline(deadline_text)
            if deadline:
                return deadline
        
        return None

    def _extract_difficulty(self, text: str) -> str:
        """Extract the difficulty level from the input text"""
        difficulty_match = re.search(r'difficulty\s+(\d+)', text, re.IGNORECASE)
        if difficulty_match:
            difficulty_level = int(difficulty_match.group(1))
            if difficulty_level <= 2:
                return 'Easy'
            elif difficulty_level == 3:
                return 'Medium'
            else:
                return 'Hard'
        return 'Medium'  # Default difficulty

    def parse_deadline(self, deadline_str: str) -> Optional[datetime]:
        """Parse deadline string to datetime object"""
        try:
            # Handle 'today' and 'tonight' specifically
            if 'today' in deadline_str.lower() or 'tonight' in deadline_str.lower():
                return datetime.now().replace(hour=23, minute=59, second=59, microsecond=0)
            
            # Use spaCy's NER to identify DATE entities
            doc = nlp(deadline_str)
            date_ent = None
            for ent in doc.ents:
                if ent.label_ == "DATE":
                    date_ent = ent.text
                    break
            
            if date_ent:
                # Use parsedatetime to parse the identified date
                time_struct, parse_status = self.cal.parse(date_ent)
                if parse_status:
                    parsed_date = datetime(*time_struct[:6])
                    # If no specific time was given, set it to end of day
                    if parsed_date.hour == 0 and parsed_date.minute == 0:
                        parsed_date = parsed_date.replace(hour=23, minute=59, second=59)
                    return parsed_date
            
            # Fallback to parsedatetime if NER fails
            time_struct, parse_status = self.cal.parse(deadline_str)
            if parse_status:
                parsed_date = datetime(*time_struct[:6])
                # If no specific time was given, set it to end of day
                if parsed_date.hour == 0 and parsed_date.minute == 0:
                    parsed_date = parsed_date.replace(hour=23, minute=59, second=59)
                return parsed_date
            
            return None
        except Exception as e:
            print(f"Error parsing deadline: {str(e)}")
            return None

    def parse_query(self, text: str) -> Tuple[Optional[datetime], Optional[str], bool, Optional[datetime]]:
        """
        Parse a natural language query to extract deadline and relation.
        Returns: (target_date, relation, is_task_query, end_date)
        """
        doc = nlp(text.lower())
        is_task = self.is_task_query(doc)
        
        # First, check if this is a task addition query
        if is_task:
            # Extract deadline from the text
            deadline_match = re.search(r'(by|due|until)\s+(.+?)(\s+with|\s*$)', text, re.IGNORECASE)
            if deadline_match:
                deadline_text = deadline_match.group(2).strip()
                target_date = self.parse_deadline(deadline_text)
                if target_date:
                    # For task queries, default to 'before' relation
                    return target_date, 'before', True, None

        # For non-task queries or if no deadline found
        target_date = None
        relation = None
        end_date = None

        # Check for specific temporal relations
        for rel, patterns in self.temporal_relations.items():
            if any(pattern in text.lower() for pattern in patterns):
                relation = rel
                break

        # If no relation found but we have date-related words, default to 'before'
        if not relation and any(pattern in text.lower() for pattern in 
                              list(self.relative_patterns.values()) + 
                              list(self.specific_days.values())):
            relation = 'before'

        # Try to extract the date if we found a relation
        if relation:
            # Look for date patterns
            for pattern_name, pattern in self.relative_patterns.items():
                if re.search(pattern, text, re.IGNORECASE):
                    target_date = self._handle_relative_time(pattern_name)
                    break

            # Look for specific days
            if not target_date:
                for day, pattern in self.specific_days.items():
                    if re.search(pattern, text, re.IGNORECASE):
                        target_date = self._handle_specific_day(day)
                        break

            # If still no target date, try parsedatetime as a fallback
            if not target_date:
                time_struct, parse_status = self.cal.parse(text)
                if parse_status:
                    target_date = datetime(*time_struct[:6])

        return target_date, relation, is_task, end_date

    def _handle_relative_time(self, pattern_name: str) -> Optional[datetime]:
        """Handle relative time patterns to compute the target date"""
        today = datetime.now()
        if pattern_name == 'today':
            return today.replace(hour=23, minute=59, second=59, microsecond=0)
        elif pattern_name == 'tomorrow':
            tomorrow = today + timedelta(days=1)
            return tomorrow.replace(hour=23, minute=59, second=59, microsecond=0)
        elif pattern_name in ['this_week', 'next_week']:
            # Assuming week starts on Monday
            start = today - timedelta(days=today.weekday())
            if pattern_name == 'next_week':
                start += timedelta(weeks=1)
            end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
            return end
        elif pattern_name in ['this_month', 'next_month']:
            if pattern_name == 'next_month':
                month = today.month % 12 + 1
                year = today.year + (today.month // 12)
            else:
                month = today.month
                year = today.year
            last_day = calendar.monthrange(year, month)[1]
            return datetime(year, month, last_day, 23, 59, 59)
        elif pattern_name == 'weekend':
            # Assuming weekend is Saturday and Sunday
            days_ahead = 5 - today.weekday()  # Saturday
            if days_ahead < 0:
                days_ahead += 7
            saturday = today + timedelta(days=days_ahead)
            sunday = saturday + timedelta(days=1)
            return sunday.replace(hour=23, minute=59, second=59, microsecond=0)
        return None

    def _handle_specific_day(self, day: str) -> Optional[datetime]:
        """Handle specific day patterns to compute the target date"""
        today = datetime.now()
        days_ahead = {
            'monday': 0,
            'tuesday': 1,
            'wednesday': 2,
            'thursday': 3,
            'friday': 4,
            'saturday': 5,
            'sunday': 6
        }.get(day.lower(), None)
        
        if days_ahead is None:
            return None
        
        days_until = days_ahead - today.weekday()
        if days_until < 0:
            days_until += 7
        target_date = today + timedelta(days=days_until)
        return target_date.replace(hour=23, minute=59, second=59, microsecond=0)
def handle_common_queries(query: str) -> Optional[List[Dict[str, Any]]]:
    """Handle common task-related queries"""
    try:
        parser = TaskParser()
        
        # Check if this is a viewing query
        viewing_indicators = ['show', 'what', 'list', 'view', 'display', 'get']
        is_viewing_query = any(indicator in query.lower() for indicator in viewing_indicators)
        
        # If it's a viewing query, handle it differently
        if is_viewing_query:
            # Get current date and end of week
            current_date = datetime.now()
            end_of_week = current_date + timedelta(days=(6 - current_date.weekday()))
            end_of_week = end_of_week.replace(hour=23, minute=59, second=59)

            if 'week' in query.lower():
                # Show tasks due this week
                response = supabase.table("Task Data") \
                    .select("*") \
                    .lte("Deadline", end_of_week.strftime("%Y-%m-%dT%H:%M:%S")) \
                    .gte("Deadline", current_date.strftime("%Y-%m-%dT%H:%M:%S")) \
                    .execute()
                return response.data
            else:
                # Show all tasks
                response = supabase.table("Task Data").select("*").execute()
                return response.data

        # For task addition queries
        target_date, relation, is_task_query, end_date = parser.parse_query(query)
        
        if is_task_query:
            task_details = parser.extract_task_details(query)
            if task_details:
                response = supabase.table("Task Data").insert(task_details).execute()
                if response.data:
                    print(f"Task '**{task_details['Task_name']}**' added successfully with deadline **{task_details['Deadline']}**, difficulty **{task_details['difficulty']}**, and Status **{task_details['Status']}**.")
                    return None
                else:
                    print("Failed to add task.")
                    return None

        # For other date-based queries
        if target_date:
            query_builder = supabase.table("Task Data").select("*")
            
            if relation == 'inclusive':
                start_of_day = target_date.replace(hour=0, minute=0, second=0)
                end_of_day = target_date.replace(hour=23, minute=59, second=59)
                query_builder = query_builder.gte("Deadline", start_of_day.strftime("%Y-%m-%dT%H:%M:%S")) \
                                           .lte("Deadline", end_of_day.strftime("%Y-%m-%dT%H:%M:%S"))
            elif relation == 'before':
                query_builder = query_builder.lte("Deadline", target_date.strftime("%Y-%m-%dT%H:%M:%S"))
            elif relation == 'after':
                query_builder = query_builder.gte("Deadline", target_date.strftime("%Y-%m-%dT%H:%M:%S"))
            elif relation == 'flexible' and end_date:
                query_builder = query_builder.gte("Deadline", target_date.strftime("%Y-%m-%dT%H:%M:%S")) \
                                           .lte("Deadline", end_date.strftime("%Y-%m-%dT%H:%M:%S"))

            response = query_builder.execute()
            return response.data

        return None

    except Exception as e:
        print(f"Error processing query: {str(e)}")
        return None

def add_task_natural(query: str) -> Optional[Dict[str, Any]]:
    """Add a task based on natural language query"""
    parser = TaskParser()
    task_details = parser.extract_task_details(query)
    if task_details:
        response = supabase.table("Task Data").insert(task_details).execute()
        if response.data:
            print(f"Task '**{task_details['Task_name']}**' added successfully with deadline **{task_details['Deadline']}** and difficulty **{task_details['difficulty']}**.")
            return response.data[0]  # Return the inserted task
        else:
            print("Failed to add task.")
            return None
    else:
        print("Failed to extract task details. Please ensure your query includes a task name and deadline.")
        return None

def view_tasks():
    """View all tasks"""
    try:
        response = supabase.table("Task Data").select("*").execute()
        tasks = response.data
        format_task_results(tasks)
    except Exception as e:
        print(f"Error fetching tasks: {str(e)}")
def edit_task():
    """Edit an existing task"""
    try:
        tasks = supabase.table("Task Data").select("*").execute().data
        if not tasks:
            print("No tasks available to edit.")
            return

        print("\n**Existing Tasks:**")
        for idx, task in enumerate(tasks, start=1):
            print(f"{idx}. {task['Task_name']} (Status: {task.get('status', 'To Do')})")

        task_number = int(input("\nEnter the number of the task you want to edit: ").strip())
        if not (1 <= task_number <= len(tasks)):
            print("Invalid task number.")
            return

        task_to_edit = tasks[task_number - 1]
        print(f"\nEditing Task: **{task_to_edit['Task_name']}**")

        # Prompt for new details
        new_task_name = input("Enter new task name (or press Enter to keep unchanged): ").strip()
        new_deadline = input("Enter new deadline (or press Enter to keep unchanged): ").strip()
        new_difficulty = input("Enter new difficulty (1=Easy, 2=Easy, 3=Medium, 4=Hard, etc.) (or press Enter to keep unchanged): ").strip()
        new_status = input("Enter new status ('To Do' or 'Completed') (or press Enter to keep unchanged): ").strip()

        updated_fields = {}
        if new_task_name:
            updated_fields['Task_name'] = new_task_name.capitalize()
        if new_deadline:
            parser = TaskParser()
            parsed_deadline = parser.parse_deadline(new_deadline)
            if parsed_deadline:
                updated_fields['Deadline'] = parsed_deadline.strftime("%Y-%m-%dT%H:%M:%S")
            else:
                print("Failed to parse the new deadline. Keeping the old deadline.")
        if new_difficulty:
            if new_difficulty.isdigit():
                difficulty_level = int(new_difficulty)
                if difficulty_level <= 2:
                    updated_fields['difficulty'] = 'Easy'
                elif difficulty_level == 3:
                    updated_fields['difficulty'] = 'Medium'
                else:
                    updated_fields['difficulty'] = 'Hard'
            else:
                print("Invalid difficulty level. Keeping the old difficulty.")
        if new_status:
            if new_status.lower() in ['to do', 'completed']:
                updated_fields['status'] = new_status.capitalize()
            else:
                print("Invalid status. Please enter 'To Do' or 'Completed'. Keeping the old status.")

        if updated_fields:
            supabase.table("Task Data").update(updated_fields).eq("id", task_to_edit['id']).execute()
            print("Task updated successfully.")
        else:
            print("No changes made to the task.")

    except Exception as e:
        print(f"Error editing task: {str(e)}")
        print(f"Error editing task: {str(e)}")

def format_task_results(tasks: List[Dict[str, Any]]):
    """Format and display task results"""
    if not tasks:
        print("No tasks found.")
        return

    sorted_tasks = sorted(tasks, key=lambda x: datetime.fromisoformat(x['Deadline']))
    current_date = datetime.now()

    print("\n**Results:**")
    for task in sorted_tasks:
        deadline_str = task['Deadline']
        try:
            deadline = datetime.fromisoformat(deadline_str)
        except ValueError:
            print(f"Invalid deadline format for task '**{task['Task_name']}**': {deadline_str}")
            continue

        # Calculate days until deadline
        days_until = (deadline.date() - current_date.date()).days

        if days_until < 0:
            days_str = f"**{abs(days_until)} days overdue**"
        elif days_until == 0:
            days_str = "**Due today**"
        else:
            days_str = f"**{days_until} day{'s' if days_until > 1 else ''} left**"

        status = task.get('Status', 'To Do')  # Changed from 'status' to 'Status'

        print(f"- **{task['Task_name']}** is due by **{deadline.strftime('%Y-%m-%d %H:%M:%S')}**. Difficulty: **{task['difficulty'].capitalize()}**. Status: **{status}**. {days_str}.")

def is_completion_indicator(query: str) -> bool:
    """Check if the query contains completion indicators"""
    completion_patterns = [
        r"i have completed",
        r"i've completed",
        r"i have done",
        r"i've done",
        r"i finished",
        r"i've finished",
        r"i completed",
        r"i've accomplished",
        r"i accomplished",
        r"i got it done",
        r"i've got it done",
        r"i managed to",
        r"i've managed to",
        r"i did",
        r"i've handled",
        r"i handled",
        r"i wrapped up",
        r"i've wrapped up",
        r"is done$",
        r"is completed$",
        r"is finished$",
        r"done$",
        r"completed$"
    ]
    
    query_lower = query.lower()
    return any(re.search(pattern, query_lower) for pattern in completion_patterns)

def handle_task_completion(query: str):
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
        
        # Remove common words and clean up the description
        common_words = {'the', 'a', 'an', 'this', 'that', 'these', 'those'}
        task_terms = [word for word in task_description.strip().split() 
                     if word not in common_words]
        
        if not task_terms:
            print("Please specify which task you completed.")
            return

        # Get all tasks from the database
        tasks = supabase.table("Task Data").select("*").execute().data
        if not tasks:
            print("No tasks available.")
            return

        # Find matching tasks based on partial name match
        matching_tasks = []
        for task in tasks:
            if any(term in task['Task_name'].lower() for term in task_terms):
                matching_tasks.append(task)

        if not matching_tasks:
            print(f"No tasks found matching '{task_terms}'.")
            return

        # If there are matching tasks, show them to the user
        print("\nFound these matching tasks:")
        for idx, task in enumerate(matching_tasks, 1):
            deadline = datetime.fromisoformat(task['Deadline'])
            print(f"{idx}. **{task['Task_name']}** (due {deadline.strftime('%Y-%m-%d %H:%M')})")

        # Ask user to confirm which task to mark as completed and delete
        while True:
            try:
                choice = input("\nEnter the number of the completed task (or press Enter to cancel): ").strip()
                
                if not choice:  # User pressed Enter without input
                    print("Operation cancelled.")
                    return
                
                choice_num = int(choice)
                if 1 <= choice_num <= len(matching_tasks):
                    task_to_delete = matching_tasks[choice_num - 1]
                    
                    # Delete the task
                    supabase.table("Task Data").delete().eq("id", task_to_delete['id']).execute()
                    print(f"Great job! Task '**{task_to_delete['Task_name']}**' has been marked as completed and removed from your list.")
                    return
                else:
                    print("Invalid number. Please try again.")
            except ValueError:
                print("Please enter a valid number.")

    except Exception as e:
        print(f"Error handling task completion: {str(e)}")

def interactive_query():
    """Interactive query interface"""
    print("\nSome example queries:")
    print("- I need to complete project by tomorrow with difficulty 3")
    print("- Show all my tasks")
    print("- What are my tasks due this week?")
    print("- I have completed the python assignment")
    print("- Delete task python")
    print("- Math assignment is done\n")

    while True:
        try:
            query = input("\nEnter your query: ").strip()
            
            if is_completion_indicator(query):
                # Handle task completion/deletion
                handle_task_completion(query)
            elif any(indicator in query.lower() for indicator in TaskParser().task_indicators) or \
                 query.lower().startswith('add'):
                # Handle task addition
                added_task = add_task_natural(query)
            elif query.lower().startswith('delete'):
                # Handle explicit deletion
                delete_task(query)
            elif query.lower().startswith('mark task'):
                # Handle marking a task as completed
                mark_task_completed(query)
            else:
                # Handle other queries
                results = handle_common_queries(query)
                if results:
                    # Format and display results
                    format_task_results(results)
                else:
                    print("No results to display.")
            
        except Exception as e:
            print(f"Error: {str(e)}")
            print("Please try again with a different query.")

def mark_task_completed(query: str):
    """Mark a specific task as completed"""
    try:
        # Extract task number from the query
        match = re.search(r'mark task (\d+) as completed', query.lower())
        if not match:
            print("Please use the format: 'Mark task <number> as completed'")
            return

        task_number = int(match.group(1))
        tasks = supabase.table("Task Data").select("*").execute().data

        if not tasks:
            print("No tasks available.")
            return

        if not (1 <= task_number <= len(tasks)):
            print("Invalid task number.")
            return

        task_to_mark = tasks[task_number - 1]
        if task_to_mark.get('Status', 'To Do') == 'Completed':
            print(f"Task '**{task_to_mark['Task_name']}**' is already completed.")
            return

        # Update the Status to "Completed"
        supabase.table("Task Data").update({"Status": "Completed"}).eq("id", task_to_mark['id']).execute()
        print(f"Task '**{task_to_mark['Task_name']}**' marked as **Completed**.")

    except Exception as e:
        print(f"Error marking task as completed: {str(e)}")

def delete_task(query: str):
    """Delete a task based on name matching"""
    try:
        # Extract the task description from the query
        task_description = query.lower().replace('delete', '', 1).strip()
        if not task_description:
            print("Please specify what task you want to delete.")
            return

        # Get all tasks from the database
        tasks = supabase.table("Task Data").select("*").execute().data
        if not tasks:
            print("No tasks available.")
            return

        # Find matching tasks based on partial name match
        matching_tasks = []
        for task in tasks:
            if task_description in task['Task_name'].lower():
                matching_tasks.append(task)

        if not matching_tasks:
            print(f"No tasks found matching '{task_description}'.")
            return

        # If there are matching tasks, show them to the user
        print("\nFound these matching tasks:")
        for idx, task in enumerate(matching_tasks, 1):
            deadline = datetime.fromisoformat(task['Deadline'])
            print(f"{idx}. **{task['Task_name']}** (due {deadline.strftime('%Y-%m-%d %H:%M')})")

        # Ask user to confirm which task to delete
        while True:
            try:
                choice = input("\nEnter the number of the task you want to delete (or press Enter to cancel): ").strip()
                
                if not choice:  # User pressed Enter without input
                    print("Deletion cancelled.")
                    return
                
                choice_num = int(choice)
                if 1 <= choice_num <= len(matching_tasks):
                    task_to_delete = matching_tasks[choice_num - 1]
                    
                    # Double-check with user before deleting
                    confirm = input(f"Are you sure you want to delete '**{task_to_delete['Task_name']}**'? (yes/no): ").strip().lower()
                    if confirm == 'yes':
                        # Delete the task
                        supabase.table("Task Data").delete().eq("id", task_to_delete['id']).execute()
                        print(f"Task '**{task_to_delete['Task_name']}**' has been deleted.")
                    else:
                        print("Deletion cancelled.")
                    return
                else:
                    print("Invalid number. Please try again.")
            except ValueError:
                print("Please enter a valid number.")

    except Exception as e:
        print(f"Error deleting task: {str(e)}")

if __name__ == "__main__":
    interactive_query()

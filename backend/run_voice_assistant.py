import logging
import time
import threading
from colorama import Fore, init
from voice_assistant.audio import record_audio, play_audio
from voice_assistant.transcription import transcribe_audio
from voice_assistant.response_generation import generate_response
from voice_assistant.text_to_speech import text_to_speech
from voice_assistant.utils import delete_file
from voice_assistant.config import Config
from voice_assistant.api_key_manager import (
    get_transcription_api_key, 
    get_response_api_key, 
    get_tts_api_key
)
import asyncio
import os
import weather
from sendEmail import AIService as EmailService,  sendemail
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from realTimeSearch import real_time_search
import todo
import webScrapeAndProcess
import json
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
init(autoreset=True)

class TaskHandler:
    """Handles different types of tasks based on user input."""
    
    def __init__(self):
        self.task_functions = {
            "WEBSEARCH": self.handle_web_search,
            "REALTIME": self.handle_real_time_search,
            "EMAIL": self.handle_email,
            "TODO": self.handle_todo,
            "WEATHER": self.handle_weather,
            "CONVERSATION": self.handle_conversation
        }

    def classify_request(self, user_prompt):
        """Classify the user's prompt to determine the task type."""
        prompt = user_prompt.lower()
        task_type = None
        details = {}

        # Define keywords and patterns for classification
        classification_patterns = {
            "WEBSEARCH": ["search", "web", "lookup", "find"],
            "REALTIME": ["realtime", "live", "current"],
            "EMAIL": ["email", "send email", "mail"],
            "TODO": ["todo", "task", "reminder"],
            "WEATHER": ["weather", "forecast"]
        }

        # Check for specific patterns first
        if "weather in" in prompt:
            task_type = "WEATHER"
            details = {"city": prompt.split("weather in")[-1].strip()}
        elif "send email" in prompt or "email" in prompt:
            task_type = "EMAIL"
        elif any(word in prompt for word in ["search", "web"]):
            task_type = "WEBSEARCH"
            details = {"query": prompt}
        elif "todo" in prompt:
            task_type = "TODO"
            details = {"query": prompt}
        elif any(word in prompt for word in ["realtime", "live"]):
            task_type = "REALTIME"
        else:
            task_type = "CONVERSATION"

        return {"type": task_type, "details": details}

    def handle_task(self, task_type, details):
        """Execute the specified task."""
        try:
            if task_type in self.task_functions:
                return self.task_functions[task_type](details)
            else:
                logging.warning(f"Unknown task type: {task_type}")
                return None

        except Exception as e:
            logging.error(f"Error handling task {task_type}: {e}")
            return None

    def handle_web_search(self, details):
        """Handle web search tasks."""
        try:
            query = details.get("query", "")
            if query:
                return webScrapeAndProcess.web_search(query)
            logging.warning("No query provided for web search")
        except Exception as e:
            logging.error(f"Error in web search: {e}")

    def handle_real_time_search(self, details):
        """Handle real-time search tasks."""
        try:
            return real_time_search()
        except Exception as e:
            logging.error(f"Error in real-time search: {e}")

    def handle_email(self, details):
        """Handle email tasks."""
        try:
            # Initialize the email service
            email_service = EmailService()
            
            print("\n=== Email Service ===")
            
            # Get email details from user with validation
            to_email = input("Enter receiver's email address: ").strip()
            while not re.match(r"[^@]+@[^@]+\.[^@]+", to_email):
                print("Invalid email format. Please try again.")
                to_email = input("Enter receiver's email address: ").strip()
            
            email_title = input("Enter email title/subject: ").strip()
            while not email_title:
                print("Title cannot be empty. Please try again.")
                email_title = input("Enter email title/subject: ").strip()
            
            sender_name = input("Enter your name: ").strip()
            while not sender_name:
                print("Name cannot be empty. Please try again.")
                sender_name = input("Enter your name: ").strip()
            
            receiver_name = input("Enter the receiver's name: ").strip()
            while not receiver_name:
                print("Receiver's name cannot be empty. Please try again.")
                receiver_name = input("Enter the receiver's name: ").strip()

            # Get user's request for email content
            email_body = input("Enter your email message: ").strip()
            while not email_body:
                print("Email message cannot be empty. Please try again.")
                email_body = input("Enter your email message: ").strip()

            # Format the email body with sender and receiver names
            formatted_body = (
                f"Dear {receiver_name},\n\n"
                f"{email_body}\n\n"
                f"Best regards,\n{sender_name}"
            )

            # Send the email using the email service
            result = asyncio.run(email_service.send_email_via_assistant(
                to_email, 
                email_title, 
                formatted_body
            ))

            if result["status"] == "success":
                logging.info("Email sent successfully")
                return f"Email sent successfully to {to_email}"
            else:
                logging.error(f"Failed to send email: {result.get('message', 'Unknown error')}")
                return "Failed to send email"
            
        except Exception as e:
            logging.error(f"Error sending email: {e}")
            return f"Failed to send email: {str(e)}"

    def handle_todo(self, details):
        """Handle todo tasks."""
        try:
            query = details.get("query", "")
            if query:
                return todo.TodoManager()(query)
            logging.warning("No query provided for todo")
        except Exception as e:
            logging.error(f"Error in todo management: {e}")

    def handle_weather(self, details):
        """Handle weather tasks."""
        try:
            city = details.get("city", "")
            if city:
                return weather.get_weather(city)
            logging.warning("No city provided for weather")
        except Exception as e:
            logging.error(f"Error getting weather: {e}")

    def handle_conversation(self, details):
        """Handle general conversation."""
        return None

def analyze_input(user_input):
    """Analyze the user input and route to appropriate handler."""
    try:
        task_handler = TaskHandler()
        task = task_handler.classify_request(user_input)
        logging.info(f"Classified task: {task['type']}")
        
        # Handle the task and get result
        result = task_handler.handle_task(task["type"], task["details"])
        
        # If it's an email task, we want to speak the result
        if task["type"] == "EMAIL":
            return result  # This will be passed back to main_loop for text-to-speech
            
    except Exception as e:
        logging.error(f"Error analyzing input: {e}")
        return str(e)

def main_loop():
    """Main loop to run the voice assistant."""
    chat_history = [
        {
            "role": "system",
            "content": """You are a helpful Assistant called OpenCode-Agent.
             You are friendly and fun and will help users with their requests.
             Your answers are short and concise. When asked questions,
             you will provide the best possible answers. You can send emails,
             search the web, check the weather, and more. You are romantic
             and friendly. eliminate the `*` when you're giving a response, this will make it easier for the user to understand because it will be translated to speech."""
        }
    ]

    while True:
        try:
            # Record audio
            record_audio(Config.INPUT_AUDIO)

            # Get transcription API key
            transcription_api_key = get_transcription_api_key()

            # Transcribe audio
            user_input = transcribe_audio(
                Config.TRANSCRIPTION_MODEL,
                transcription_api_key,
                Config.INPUT_AUDIO,
                Config.LOCAL_MODEL_PATH
            )

            if not user_input:
                logging.info("No transcription returned. Restarting recording.")
                continue

            logging.info(Fore.GREEN + f"You said: {user_input}" + Fore.RESET)

            if any(word in user_input.lower() for word in ["goodbye", "arrivederci"]):
                break

            # Analyze input and get result
            analysis_result = analyze_input(user_input)
            
            # If we got a result from task handling (like email confirmation),
            # use it as the response
            if analysis_result:
                response_text = analysis_result
            else:
                # Otherwise, generate response using chat
                chat_history.append({"role": "user", "content": user_input})
                response_api_key = get_response_api_key()
                response_text = generate_response(
                    Config.RESPONSE_MODEL,
                    response_api_key,
                    chat_history,
                    Config.LOCAL_MODEL_PATH
                )
                chat_history.append({"role": "assistant", "content": response_text})

            logging.info(Fore.CYAN + f"Response: {response_text}" + Fore.RESET)

            # Prepare output file
            output_file = 'output.mp3' if Config.TTS_MODEL in [
                'openai', 'elevenlabs', 'melotts', 'cartesia'] else 'output.wav'

            # Get TTS API key
            tts_api_key = get_tts_api_key()

            # Convert text to speech
            text_to_speech(
                Config.TTS_MODEL,
                tts_api_key,
                response_text,
                output_file,
                Config.LOCAL_MODEL_PATH
            )

            # Play audio
            if Config.TTS_MODEL != "cartesia":
                play_audio(output_file)

            # Clean up
            delete_file(Config.INPUT_AUDIO)
            delete_file(output_file)

        except Exception as e:
            logging.error(Fore.RED + f"An error occurred: {e}" + Fore.RESET)
            delete_file(Config.INPUT_AUDIO)
            if 'output_file' in locals():
                delete_file(output_file)
            time.sleep(1)

def main():
    """Main function to start the main loop in a separate thread."""
    main_thread = threading.Thread(target=main_loop)
    main_thread.start()
    main_thread.join()

if __name__ == "__main__":
    main()

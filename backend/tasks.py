import json
import logging
import uuid
from typing import Dict, Any
import asyncio
from Rag import RAGProcessor  # Changed from RAG to RAGProcessor
from realTimeSearch import real_time_search
from weather import get_weather
from todo import TodoManager 
from sendEmail import AIService as EmailService, test_service as send_email_interactive
from webScrapeAndProcess import web_search
# from Audio import speak
import os
from voice_assistant.transcription import transcribe_audio
from voice_assistant.response_generation import generate_response
from sendEmail import AIService as EmailService, test_service as send_email_interactive
from voice_assistant.config import Config as config
from voice_assistant.api_key_manager import get_response_api_key
from weather import get_weather
from run_voice_assistant import assistant

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
import json
with open('credentials.json') as f:
    credentials = json.load(f)  # Added credentials

with open('token.json') as f:
    token = json.load(f)  # Added token
import voice_assistant.config as config

class TaskRouter:
    def __init__(self):
        self.email_service = EmailService()  # Changed from AIService to EmailService
        self.todo_manager = TodoManager()
        self.rag_processor = RAGProcessor()  # Changed from RAG() to RAGProcessor()
        self.get_weather = get_weather()  # Added weather
        self.assistant = assistant()  # Added assistant
        
        # Initialize AI models - No Gemini
        
        pass # No Gemini model needed here

    def classify_request(self, user_prompt: str) -> Dict[str, Any]:
        """Classifies user prompt to determine task type."""
        prompt_lower = user_prompt.lower()
        if "search" in prompt_lower:
            if "web" in prompt_lower:
                return {"type": "WEBSEARCH", "details": {"query": user_prompt}}
            return {"type": "REALTIME", "details": {}} # Real-time search doesn't need query
        elif "email" in prompt_lower or "send email" in prompt_lower:
            return {"type": "EMAIL", "details": {}}
        elif "todo" in prompt_lower:
            return {"type": "TODO", "details": {"query": user_prompt}}
        elif "weather" in prompt_lower: # Added weather
            return {"type": "WEATHER", "details": {"city": prompt_lower.split("weather in")[-1].strip() if "weather in" in prompt_lower else ""}}
        else:
            return {"type": "CONVERSATION", "details": {}}


    async def analyze_prompt_and_route_task(self, user_prompt: str) -> Dict[str, Any]:
        """Analyzes user prompt and routes to appropriate function"""
        try:
            logger.info(f"Processing prompt: {user_prompt}")
            
            # Classify input based on keywords
            classification = self.classify_request(user_prompt)
            
            logger.info(f"Classification: {classification}")
            
            # Route based on classification
            match classification["type"].upper():
                case "REALTIME":
                    return await real_time_search(user_prompt)
                    
                case "WEBSEARCH":
                    search_query = classification["details"]["query"]
                    logger.info(f"Performing web search for: {search_query}")
                    return await web_search(search_query)
                    
                case "EMAIL":
                    return await send_email_interactive(user_prompt)
                    
                case "TODO":
                    return await self.todo_manager.process_natural_language_request(
                        classification["details"]["query"]
                    )
                case "WEATHER": # Added weather case
                    city = classification["details"]["city"]
                    logger.info(f"Fetching weather for: {city}")
                    return await get_weather(city)

                case "CONVERSATION":
                    # Use response_generation.py for conversation
                    response_api_key = get_response_api_key()
                    chat_history = []  # Initialize chat history
                    chat_response = generate_response(config.RESPONSE_MODEL, response_api_key, chat_history, config.LOCAL_MODEL_PATH)
                    return {
                        "status": "success", 
                        "response": chat_response
                    }
                    
                case _:
                    logger.error(f"Unknown request type: {classification['type']}")
                    # Default bot response for unknown requests
                    response_api_key = get_response_api_key()
                    chat_history = [{"role": "user", "content": "Respond as a helpful bot as you don't understand the request"}]
                    chat_response = generate_response(config.RESPONSE_MODEL, response_api_key, chat_history, config.LOCAL_MODEL_PATH)
                    return {
                        "status": "error",
                        "message": chat_response
                    }

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {str(e)}")
            return {"status": "error", "message": "Failed to parse response"}
        except KeyError as e:
            logger.error(f"Missing required field: {str(e)}")
            return {"status": "error", "message": f"Missing required field: {str(e)}"}
        except Exception as e:
            logger.error(f"Error processing request: {str(e)}", exc_info=True)
            return {
                "status": "error", 
                "message": f"Error processing request: {str(e)}"
            }

# Initialize router
task_router = TaskRouter()

# Main entry point
async def route_task(user_prompt: str) -> Dict[str, Any]:
    """Main entry point for task routing"""
    return await task_router.analyze_prompt_and_route_task(user_prompt)

# async def main():
#     while True:
#         try:
#             user_prompt = input(transcribe_audio(config.TRANSCRIPTION_MODEL, get_response_api_key(), config.INPUT_AUDIO, config.LOCAL_MODEL_PATH))
#             if user_prompt.lower() == 'exit':
#                 break
                
#             response = await route_task(user_prompt)
#             print("\nResponse:", json.dumps(response, indent=2))
            
#         except KeyboardInterrupt:
#             break
#         except Exception as e:
#             print(f"Error: {e}")

# if __name__ == "__main__":
#     asyncio.run(main())

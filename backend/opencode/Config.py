import logging
import re
import asyncio
import os
import sys
from typing import Dict, Any
from dotenv import load_dotenv
from livekit.plugins import openai, deepgram, elevenlabs, cartesia

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from voice_assistant.config import Config

# this is  where i am configuring my api for tts and stt for livekit, it will be using google_gemini, elevenlabs, grok, openai, and cartesia
def generate_response(model: str, api_key: str, chat_history: list, local_model_path: str = None):
    """
    Generate a response using the specified model.
    
    Args:
        model (str): The model to use for response generation ('openai', 'groq', 'local').
        api_key (str): The API key for the response generation service.
        chat_history (list): The chat history as a list of messages.
        local_model_path (str): The path to the local model (if applicable).
    
    Returns:
        str: The generated response text.
    """
    try:
        if model == 'openai':
            return openai.LLM(api_key, chat_history)
        elif model == 'groq':
            return openai.LLM.with_groq(api_key, chat_history)
        elif model == 'ollama':
            return openai.LLM.with_ollama(chat_history)
        elif model == 'local':
            # Placeholder for local LLM response generation
            return "Generated response from local model"
        else:
            raise ValueError("Unsupported response generation model")
    except Exception as e:
        logging.error(f"Failed to generate response: {e}")
        return "Error in generating response"
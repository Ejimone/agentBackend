import logging
import time
from colorama import Fore, init
from voice_assistant.audio import record_audio, play_audio
from voice_assistant.transcription import transcribe_audio
from voice_assistant.response_generation import generate_response
from voice_assistant.text_to_speech import text_to_speech
from voice_assistant.utils import delete_file
from voice_assistant.config import Config
from voice_assistant.api_key_manager import get_transcription_api_key, get_response_api_key, get_tts_api_key
import os
import weather
from sendEmail import AIService as EmailService, sendemail
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from realTimeSearch import real_time_search
import todo
import webScrapeAndProcess
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize colorama
init(autoreset=True)

import threading

def classify_request(user_prompt):
    """
    Classifies user prompt to determine task type.
    """
    prompt = user_prompt.lower()
    if "search" in prompt:
        if "web" in prompt:
            return {"type": "WEBSEARCH", "details": {"query": user_prompt}}
        return {"type": "REALTIME", "details": {}}  # Real-time search doesn't need query
    elif "email" in prompt or "send email" in prompt:
        sendemail()
    elif "todo" in prompt:
        return {"type": "TODO", "details": {"query": user_prompt}}
    elif "weather" in prompt:
        return {"type": "WEATHER", "details": {"city": prompt.split("weather in")[-1].strip() if "weather in" in prompt else ""}}
    else:
        return {"type": "CONVERSATION", "details": {}}

def analyze_input(user_input):
    """
    Analyze the user input and call the appropriate function.
    """
    task = classify_request(user_input)
    if task["type"] == "WEBSEARCH":
        webScrapeAndProcess.web_search(task["details"]["query"])
    elif task["type"] == "REALTIME":
        real_time_search()
    elif task["type"] == "EMAIL":
        sendemail()
    elif task["type"] == "TODO":
        todo.TodoManager()
    elif task["type"] == "WEATHER":
        weather.get_weather(task["details"]["city"])
    else:
        pass

def main():
    """
    Main function to run the voice assistant.
    """
    chat_history = [
        {"role": "system", "content": """ You are a helpful Assistant called OpenCode-Agent. 
         You are friendly and fun and you will help the users with their requests.
         Your answers are short and concise. """}
    ]

    while True:
        try:
            # Record audio from the microphone and save it as 'test.wav'
            record_audio(Config.INPUT_AUDIO)

            # Get the API key for transcription
            transcription_api_key = get_transcription_api_key()
            
            # Transcribe the audio file
            user_input = transcribe_audio(Config.TRANSCRIPTION_MODEL, transcription_api_key, Config.INPUT_AUDIO, Config.LOCAL_MODEL_PATH)

            # Check if the transcription is empty and restart the recording if it is. This check will avoid empty requests if vad_filter is used in the fastwhisperapi.
            if not user_input:
                logging.info("No transcription was returned. Starting recording again.")
                continue
            logging.info(Fore.GREEN + "You said: " + user_input + Fore.RESET)

            # Check if the user wants to exit the program
            if "goodbye" in user_input.lower() or "arrivederci" in user_input.lower():
                break

            # Analyze the user input and call the appropriate function
            analyze_input(user_input)

            # Append the user's input to the chat history
            chat_history.append({"role": "user", "content": user_input})

            # Get the API key for response generation
            response_api_key = get_response_api_key()

            # Generate a response
            response_text = generate_response(Config.RESPONSE_MODEL, response_api_key, chat_history, Config.LOCAL_MODEL_PATH)
            logging.info(Fore.CYAN + "Response: " + response_text + Fore.RESET)

            # Append the assistant's response to the chat history
            chat_history.append({"role": "assistant", "content": response_text})

            # Determine the output file format based on the TTS model
            if Config.TTS_MODEL == 'openai' or Config.TTS_MODEL == 'elevenlabs' or Config.TTS_MODEL == 'melotts' or Config.TTS_MODEL == 'cartesia':
                output_file = 'output.mp3'
            else:
                output_file = 'output.wav'

            # Get the API key for TTS
            tts_api_key = get_tts_api_key()

            # Convert the response text to speech and save it to the appropriate file
            text_to_speech(Config.TTS_MODEL, tts_api_key, response_text, output_file, Config.LOCAL_MODEL_PATH)

            # Play the generated speech audio
            if Config.TTS_MODEL == "cartesia":
                pass
            else:
                play_audio(output_file)
            
            # Clean up audio files
            # delete_file(Config.INPUT_AUDIO)
            # delete_file(output_file)

        except Exception as e:
            logging.error(Fore.RED + f"An error occurred: {e}" + Fore.RESET)
            delete_file(Config.INPUT_AUDIO)
            if 'output_file' in locals():
                delete_file(output_file)
            time.sleep(1)

if __name__ == "__main__":
    main()

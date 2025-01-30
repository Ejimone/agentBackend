import google.generativeai as genai
import speech_recognition as sr
import os
import json
import asyncio
from faster_whisper import WhisperModel
import pyaudio
import time
from openai import OpenAI
from dotenv import load_dotenv
import google.cloud.speech_v1p1beta1 as speech
from google.cloud import speech_v1p1beta1 as speech
from google.cloud import texttospeech
from google.oauth2 import service_account
from weather import get_weather
from sendEmail import * # Import the AIService class from sendEmail.py,  has functions to send_email, test_service, get_gmail_service, and the main function which was used to test the class, which could be modified to be used
from tasks import TaskRouter
from todo import TodoManager
from webScrapeAndProcess import web_search, scrape_and_summarize
from sendEmail import EmailService



load_dotenv()


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
credentials_path = "./credentials.json"
if not os.path.exists(credentials_path):
    raise FileNotFoundError(f"Credentials file not found at {credentials_path}")

credentials = service_account.Credentials.from_service_account_file(credentials_path)
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set")

speech_client = speech.SpeechClient(credentials=credentials)
tts_client = texttospeech.TextToSpeechClient(credentials=credentials)

wakeword = "boom"
listening_for_wakeword = True

client = OpenAI(api_key=OPENAI_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)

whisper_size = "base"  # or "small", "medium", "large-v1", "large-v2"
num_cores = os.cpu_count()
whisper_model = WhisperModel(whisper_size, device="cpu", compute_type="int8", cpu_threads=num_cores, num_workers=num_cores)




num_cores = os.cpu_count()
whisper_model = WhisperModel(
    whisper_size,
    device="cpu",
    compute_type="int8",
    cpu_threads=num_cores,
    num_workers=num_cores
)
generation_config = {
    "temperature":0.7,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
}

safety_settings = [
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_NONE"
    },
    {
        "category": "HARM_CATEGORY_HATE_SPEECH",
        "threshold": "BLOCK_NONE"
    },
    {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "BLOCK_NONE"
    },
    {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "BLOCK_NONE"
    },
]


model = genai.GenerativeModel(
    'gemini-1.5-flash',
    generation_config=generation_config,
    safety_settings=safety_settings
)
r = sr.Recognizer()
source = sr.Microphone()
convo= model.start_chat()
system_message =  '''INSTRUCTIONS: Do not respond to messages in a way that would reveal personal information, or a too long  format response, you can also be affirmative or negative, this if for token generation purposes.
SYSTEM MESSAGE: You're a being used for Voice Assistant and AI agent ans should respond as so., As an agent, you should be able to respond to any question or statement that is asked of you or tasked to you. You generate words in a user-friendly manner. You can also ask questions to the user to get more information, be playful alsyou generate workds of valur prioritising logic and facts'''
system_message= system_message.replace("\n", "")

def speak(text):
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US", 
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16
    )
    
    response = tts_client.synthesize_speech(
        input=synthesis_input, 
        voice=voice, 
        audio_config=audio_config
    )
    
    # Play audio
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, 
                    channels=1, 
                    rate=24000, 
                    output=True)
    stream.write(response.audio_content)
    stream.stop_stream()
    stream.close()
    p.terminate()


def wav_to_text(audio_path):
    segments,_ = whisper_model.transcribe(audio_path)
    text = "".join(segment.text for segment in segments)
    text = text.replace("*", "")  # Remove asterisks from the transcribed text
    return text

def listen_for_wake_word(audio):
    audio_content = speech.RecognitionAudio(content=audio.get_wav_data())
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        language_code="en-US"
    )
    
    response = speech_client.recognize(config=config, audio=audio_content)
    
    for result in response.results:
        transcript = result.alternatives[0].transcript
        print(f"Detected transcript: {transcript}")  # Debug print
        if wakeword.lower() in transcript.lower():
            return True
    return False

def prompt_gpt(audio):
    global listening_for_wakeword
    try:
        prompt_audio_path = "prompt.wav"
        with open(prompt_audio_path, "wb") as f:
            f.write(audio.get_wav_data())
        prompt_text = wav_to_text(prompt_audio_path)

        if not prompt_text.strip():
            speak("Empty prompt, please speak again")
            print("Empty prompt, please speak again")
            return

        print("User: ", prompt_text)
        convo.send_message(prompt_text)
        output = convo.last.text
        output = output.replace("*", "")  # Remove asterisks
        print("OpenCode: ", output)
        speak(output)

        if "thank you for your help" in prompt_text.lower():
            print("Conversation ended by user.")
            speak("You're welcome! Have a great day!")
            listening_for_wakeword = True
        else:
            print(f"\nSay {wakeword} to wake me up")
    except Exception as e:
        print("Error: ", e)
        speak("I am sorry, I could not understand you, please try again")

async def listen_and_route_tasks():
    task_manager = TaskRouter()  # Initialize TaskRouter without arguments

    def callback(recognizer, audio):
        global listening_for_wakeword
        if listening_for_wakeword:
            if listen_for_wake_word(audio):
                print("Wake word detected, ready for your command.")
                listening_for_wakeword = False
        else:
            try:
                prompt_audio_path = "prompt.wav"
                with open(prompt_audio_path, "wb") as f:
                    f.write(audio.get_wav_data())
                prompt_text = wav_to_text(prompt_audio_path)

                if not prompt_text.strip():
                    speak("Empty prompt, please speak again")
                    print("Empty prompt, please speak again")
                    return

                print("User: ", prompt_text)
                result = asyncio.run(task_manager.analyze_prompt_and_route_task(prompt_text))
                if result.get("status") == "error":
                    speak(f"Error: {result['message']}")
                else:
                    speak(result.get("response", "Task completed successfully"))

                if "thank you for your help" in prompt_text.lower():
                    print("Conversation ended by user.")
                    speak("You're welcome! Have a great day!")
                    listening_for_wakeword = True
                else:
                    print(f"\nSay {wakeword} to wake me up")
            except Exception as e:
                print("Error: ", e)
                speak("I am sorry, I could not understand you, please try again")

    with source as s:
        r.adjust_for_ambient_noise(s, duration=2)
    print("Say", wakeword, "to wake me up")
    r.listen_in_background(source, callback)
    while True:
        await asyncio.sleep(0.1)

if __name__ == "__main__":
    asyncio.run(listen_and_route_tasks())

    
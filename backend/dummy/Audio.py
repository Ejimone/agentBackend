from faster_whisper import WhisperModel
import asyncio
import json
import os
from dataclasses import dataclass
from typing import Dict, Optional
from exceptions import VoiceServiceError
from security import validate_credentials
from openai import OpenAI
import google.generativeai as genai
import pyaudio
import speech_recognition as sr
from dotenv import load_dotenv
from google.cloud import speech_v1p1beta1 as speech
from google.cloud import texttospeech
from google.oauth2 import service_account
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import Any, Dict
import logging


# Local imports
from tasks import TaskRouter
from sendEmail import EmailService
from weather import WeatherService
from Ai import AIAssistant as AIService

load_dotenv()
logger = logging.getLogger(__name__)


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


# # Configuration
# @dataclass(frozen=True)
# class VoiceConfig:
#     """Immutable voice configuration parameters"""
#     WAKE_WORD: str = "boom"
#     LANGUAGE_CODE: str = "en-US"
#     SAMPLING_RATE: int = 16000
#     CHUNK_SIZE: int = 1024
#     MAX_RETRIES: int = 3
#     AUDIO_FORMAT: int = pyaudio.paInt16
#     CHANNELS: int = 1

#     @property
#     def TTS_VOICE(self) -> texttospeech.VoiceSelectionParams:
#         """Get TTS voice configuration"""
#         return texttospeech.VoiceSelectionParams(
#             language_code="en-US",
#             name="en-US-Wavenet-D",
#             ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
#         )

#     @property
#     def TTS_AUDIO_CONFIG(self) -> texttospeech.AudioConfig:
#         """Get TTS audio configuration"""
#         return texttospeech.AudioConfig(
#             audio_encoding=texttospeech.AudioEncoding.LINEAR16
#         )

# class VoiceServiceError(Exception):
#     """Base exception for voice service errors"""
#     pass

# class VoiceInteractionService:
#     """Production-grade voice interaction service"""
    
#     def __init__(self, config: VoiceConfig = VoiceConfig()):
#         self.config = config
#         self._validate_environment()
#         self._initialize_services()
#         self.listening_for_wakeword = True
#         self.recognizer = sr.Recognizer()
#         self.microphone = sr.Microphone()
#         self.audio_interface = pyaudio.PyAudio()

#     def _validate_environment(self) -> None:
#         """Validate required environment setup"""
#         required_vars = ['GEMINI_API_KEY', 'OPENWEATHER_API_KEY']
#         missing_vars = [var for var in required_vars if not os.getenv(var)]
#         if missing_vars:
#             raise VoiceServiceError(f"Missing environment variables: {', '.join(missing_vars)}")

#     def _initialize_services(self) -> None:
#         """Initialize external service clients"""
#         try:
#             # Initialize AI Services
#             self.ai_service = AIService()
#             self.weather_service = WeatherService()
#             self.email_service = EmailService()

#             # Initialize Google services
#             self.speech_client = speech.SpeechClient(
#                 credentials=validate_credentials()
#             )
#             self.tts_client = texttospeech.TextToSpeechClient(
#                 credentials=validate_credentials()
#             )

#             # Initialize AI models
#             genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
#             self.gemini_model = genai.GenerativeModel('gemini-1.5-flash')

#         except Exception as e:
#             logger.error("Service initialization failed: %s", e)
#             raise VoiceServiceError("Service initialization failed") from e

#     @retry(
#         stop=stop_after_attempt(VoiceConfig.MAX_RETRIES),
#         wait=wait_exponential(multiplier=1, min=2, max=10)
#     )
#     async def process_audio_input(self, audio_data: bytes) -> Optional[Dict]:
#         """Process audio input with retry logic"""
#         try:
#             text = await self._transcribe_audio(audio_data)
#             if not text:
#                 return None

#             return await self.route_task(text)
            
#         except Exception as e:
#             logger.error("Audio processing error: %s", e)
#             raise VoiceServiceError("Audio processing failed") from e

#     async def _transcribe_audio(self, audio_data: bytes) -> Optional[str]:
#         """Transcribe audio to text with validation"""
#         try:
#             audio = speech.RecognitionAudio(content=audio_data)
#             config = speech.RecognitionConfig(
#                 encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
#                 sample_rate_hertz=VoiceConfig.SAMPLING_RATE,
#                 language_code=VoiceConfig.LANGUAGE_CODE
#             )

#             response = await self.speech_client.recognize(
#                 config=config,
#                 audio=audio
#             )
#             return self._parse_transcription(response)
            
#         except Exception as e:
#             logger.error("Transcription error: %s", e)
#             return None

#     def _parse_transcription(self, response) -> Optional[str]:
#         """Parse and validate transcription response"""
#         for result in response.results:
#             if result.alternatives:
#                 return result.alternatives[0].transcript.strip()
#         return None

#     async def route_task(self, text: str) -> Dict:
#         """Route processed text to appropriate service"""
#         try:
#             if self.config.WAKE_WORD.lower() in text.lower():
#                 return await self.handle_wake_word()
                
#             return await self.ai_service.process_command(text)
            
#         except Exception as e:
#             logger.error("Task routing error: %s", e)
#             return {
#                 "status": "error",
#                 "message": "Failed to process request"
#             }

#     async def text_to_speech(self, text: str) -> None:
#         """Convert text to speech with proper async handling"""
#         try:
#             synthesis_input = texttospeech.SynthesisInput(text=text)
#             response = await self.tts_client.synthesize_speech(
#                 input=synthesis_input,
#                 voice=self.config.TTS_VOICE,
#                 audio_config=self.config.TTS_AUDIO_CONFIG
#             )
            
#             await self._play_audio(response.audio_content)
            
#         except Exception as e:
#             logger.error("TTS error: %s", e)
#             raise VoiceServiceError("Text-to-speech failed") from e

#     async def _play_audio(self, audio_content: bytes) -> None:
#         """Play audio content asynchronously"""
#         try:
#             stream = self.audio_interface.open(
#                 format=self.config.AUDIO_FORMAT,
#                 channels=self.config.CHANNELS,
#                 rate=24000,
#                 output=True
#             )
            
#             await asyncio.get_event_loop().run_in_executor(
#                 None, 
#                 lambda: stream.write(audio_content)
#             )
            
#             stream.stop_stream()
#             stream.close()
            
#         except Exception as e:
#             logger.error("Audio playback error: %s", e)
#             raise VoiceServiceError("Audio playback failed") from e

#     async def run(self) -> None:
#         """Main service execution loop"""
#         try:
#             with self.microphone as source:
#                 self.recognizer.adjust_for_ambient_noise(source)
#                 print(f"System ready. Say '{self.config.WAKE_WORD}' to activate.")
                
#                 while True:
#                     audio = self.recognizer.listen(source)
#                     result = await self.process_audio_input(audio.get_wav_data())
                    
#                     if result and result.get("status") == "success":
#                         await self.text_to_speech(result.get("response"))
                        
#                     await asyncio.sleep(0.1)
                    
#         except KeyboardInterrupt:
#             print("\nShutting down voice service...")
#         finally:
#             self.audio_interface.terminate()

# if __name__ == "__main__":
#     service = VoiceInteractionService()
#     asyncio.run(service.run())
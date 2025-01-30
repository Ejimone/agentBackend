import os
import logging
from dotenv import load_dotenv
load_dotenv()
from Gemini import *
from deepgram.utils import verboselogs


from deepgram import (
    DeepgramClient,
    SpeakOptions,
)

# SPEAK_TEXT = {"text": "Hello world!"}
filename = "output.mp3"


def TTX(text):
    SPEAK_TEXT = {"text": text}
    try:
        # STEP 1 Create a Deepgram client using the API key from environment variables
        deepgram = DeepgramClient(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
        )

        # STEP 2 Call the save method on the speak property
        options = SpeakOptions(
            model="aura-asteria-en",
            encoding="linear16",
        
        )

        response = deepgram.speak.rest.v("1").save(filename, SPEAK_TEXT, options)
        print(response.to_json(indent=4))

    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    input_text = input("Enter text to convert to speech: ")
    TTX(input_text)
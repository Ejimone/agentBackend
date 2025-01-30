# text_to_speech.py
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs import play
import os

load_dotenv()

def tts(text: str) -> None:
    """
    Convert text to speech and play it
    
    Args:
        text: Text to convert to speech
    """
    try:
        client = ElevenLabs(
            api_key=os.getenv("ELEVENLABS_API_KEY"),
        )
        
        audio = client.text_to_speech.convert(
            voice_id="JBFqnCBsd6RMkjVDRZzb",
            output_format="mp3_44100_128",
            text=text,
            model_id="eleven_multilingual_v2",
        )

        play(audio)
        
    except Exception as e:
        print(f"Error in text-to-speech: {str(e)}")

# Only run this if the file is run directly
if __name__ == "__main__":
    test = input("Enter text to convert to speech: ")
    tts(test)



# elevenlabs.set_api_key(os.getenv("ELEVENLABS_API_KEY"))
# load_dotenv()
# ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")


# client = ElevenLabs()

# audio = client.text_to_speech.convert(
#     text="The first move is what sets everything in motion.",
#     voice_id="JBFqnCBsd6RMkjVDRZzb",
#     model_id="eleven_multilingual_v2",
#     output_format="mp3_44100_128",
# )

# play(audio)

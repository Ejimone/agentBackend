# Ai.py
import asyncio
import time
from typing import Optional
from text_to_speech import tts as text_to_speech
from llm import DualAIChatBot
from speech_to_text_streaming import get_transcript, transcript_collector

# Initialize AI agent
agent = DualAIChatBot()

async def handle_llm_response(prompt: str) -> None:
    """Process user input and generate voice response"""
    if not prompt.strip():
        return
    
    print(f"User: {prompt}")
    response = agent.generate_response(
        prompt,
        model="gpt-4",
        temperature=0.5,
        max_tokens=500
    )
    print(f"AI: {response}")
    text_to_speech(response)

async def continuous_conversation_loop():
    """Main loop for voice interactions"""
    last_activity_time = time.time()
    active_transcription = False
    
    while True:
        try:
            # Start transcription session
            transcription_task = asyncio.create_task(get_transcript())
            active_transcription = True
            print("\nListening... (say 'exit' to quit)")
            
            while True:
                await asyncio.sleep(0.1)
                current_transcript = transcript_collector.get_full_transcript()
                
                # Check for exit command
                if "exit" in current_transcript.lower():
                    print("Exiting conversation loop...")
                    return
                
                # Detect pause threshold (1.5 seconds)
                if current_transcript:
                    last_activity_time = time.time()
                elif time.time() - last_activity_time > 1.5 and active_transcription:
                    # Process the completed transcript
                    if current_transcript:
                        await handle_llm_response(current_transcript)
                    # Reset for next interaction
                    transcript_collector.reset()
                    transcription_task.cancel()
                    active_transcription = False
                    break
                    
        except asyncio.CancelledError:
            # Normal cancellation when switching turns
            pass
        except Exception as e:
            print(f"Error in conversation loop: {str(e)}")
            await asyncio.sleep(1)  # Prevent tight error loop

if __name__ == "__main__":
    asyncio.run(continuous_conversation_loop())
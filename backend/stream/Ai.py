# Ai.py
import asyncio
from text_to_speech import tts
from llm import DualAIChatBot
from speech_to_text_streaming import transcript_collector, get_transcript

class ConversationManager:
    def __init__(self):
        self.agent = DualAIChatBot()
        self.is_listening = True

    async def process_speech_to_response(self, transcript: str) -> None:
        """Handle the complete flow from transcript to voice response"""
        try:
            # Generate LLM response
            print(f"\nProcessing: {transcript}")
            response = self.agent.generate_response(
                transcript,
                model="gpt-4",
                temperature=0.5,
                max_tokens=500
            )
            print(f"AI Response: {response}")

            # Convert response to speech
            tts(response)

        except Exception as e:
            print(f"Error processing response: {str(e)}")

    async def handle_transcription(self):
        print("Starting transcription loop...")
        while self.is_listening:
            transcript = await transcript_collector.transcript_queue.get()
            if not transcript:
                continue

            print(f"Transcript received: {transcript}")

            if "exit" in transcript.lower():
                self.is_listening = False
                print("Exiting conversation...")
                break

            await self.process_speech_to_response(transcript)

async def main():
    """Main entry point for the conversation system"""
    manager = ConversationManager()

    print("Starting conversation... (say 'exit' to quit)")

    # Create event loop for clean shutdown
    transcription_task = asyncio.create_task(get_transcript())
    conversation_task = asyncio.create_task(manager.handle_transcription())

    try:
        await conversation_task
    except asyncio.CancelledError:
        pass
    finally:
        transcription_task.cancel()
        await asyncio.gather(transcription_task, return_exceptions=True)
        print("\nConversation ended")

if __name__ == "__main__":
    asyncio.run(main())

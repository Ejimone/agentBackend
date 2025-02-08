import logging
import re
import asyncio
import os
import sys
from typing import Dict, Any
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# LiveKit imports
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
)
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import silero, openai, elevenlabs, deepgram

# Local imports
from dummy.realtimeSearch import real_time_search
import todo
from webScrapeAndProcess import WebScraper
from sendEmail import AIService as EmailService
from weather import WeatherService
from sendEmail import sendEmail
from voice_assistant.config import Config

load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("voice-agent")

class TaskRouter:
    def __init__(self):
        self.config = Config()
        self.email_service = EmailService()
        self.weather_service = WeatherService()
        self.web_scraper = WebScraper()
        self.task_handlers = {
            "WEBSEARCH": self._handle_web_search,
            "REALTIME": self._handle_real_time,
            "EMAIL": self._handle_email,
            "TODO": self._handle_todo,
            "WEATHER": self._handle_weather,
            "WEBSCRAPE": self._handle_web_scrape,
            "CONVERSATION": self._handle_conversation
        }

    def classify_request(self, text: str) -> Dict[str, Any]:
        """Classify user input into specific task types with context extraction."""
        text = text.lower()
        task_type = "CONVERSATION"
        details = {}

        patterns = {
            "WEATHER": {
                "keywords": ["weather", "temperature", "forecast"],
                "context": r"weather (?:in|at|for) ([\w\s,]+)"
            },
            "EMAIL": {
                "keywords": ["email", "send mail", "compose"],
                "context": r"to (\w+@\w+\.\w+)"
            },
            "WEBSEARCH": {
                "keywords": ["search", "lookup", "find information"],
                "context": r"for ([\w\s]+)"
            },
            "WEBSCRAPE": {
                "keywords": ["scrape", "extract", "analyze url"],
                "context": r"(https?://\S+)"
            },
            "TODO": {
                "keywords": ["todo", "task", "reminder"],
                "context": r"add ([\w\s]+)"
            },
            "REALTIME": {
                "keywords": ["realtime", "current", "now"],
                "context": r"information on ([\w\s]+)"
            }
        }

        for task_name, pattern in patterns.items():
            if any(kw in text for kw in pattern["keywords"]):
                task_type = task_name
                match = re.search(pattern["context"], text)
                if match:
                    details = {"query": match.group(1).strip()}
                break

        return {"type": task_type, "details": details}

    async def handle_task(self, task_type: str, details: Dict[str, Any], agent: VoicePipelineAgent) -> str:
        """Orchestrate task handling with proper timeouts and error management."""
        try:
            handler = self.task_handlers.get(task_type, self._handle_conversation)
            return await asyncio.wait_for(
                handler(details, agent),
                timeout=self.config.TASK_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.error(f"Task {task_type} timed out after {self.config.TASK_TIMEOUT}s")
            return "This request is taking longer than expected. Please try again."
        except Exception as e:
            logger.error(f"Task error: {str(e)}")
            return f"Sorry, I encountered an error: {str(e)}"

    async def _handle_web_search(self, details: Dict[str, Any], agent: VoicePipelineAgent) -> str:
        """Process web search requests with result summarization."""
        query = details.get("query", "")
        if not query:
            return "Please provide a search query."

        results = await self.web_scraper.web_search(query)
        return self._format_search_results(results)

    async def _handle_email(self, details: Dict[str, Any], agent: VoicePipelineAgent) -> str:
        """Handle email composition and sending with confirmation flow."""
        email_data = await self._generate_email_content(details, agent)
        result = await self.email_service.send_email_via_assistant(**email_data)
        if result["status"] == "success":
            return "Email sent successfully!"
        else:
            return f"Failed to send email: {result.get('message', 'Unknown error')}"

    async def _handle_weather(self, details: Dict[str, Any], agent: VoicePipelineAgent) -> str:
        """Fetch and format weather information for a given location."""
        location = details.get("query", "")
        if not location:
            return "Please specify a location for the weather."

        weather_data = await self.weather_service.get_weather(location)
        if weather_data and weather_data.get("status") == "success":
            weather = weather_data["data"]
            return (
                f"Weather in {weather['location']}:\n"
                f"Temperature: {weather['temperature']}°C, "
                f"Conditions: {weather['conditions']}"
            )
        else:
            return "Could not retrieve weather information."

    async def _handle_web_scrape(self, details: Dict[str, Any], agent: VoicePipelineAgent) -> str:
        """Scrape content from a URL and provide a summary."""
        url = details.get("query", "")
        if not url:
            return "Please provide a URL to scrape."

        result = await self.web_scraper.scrape_and_summarize(url)
        if result.get("status") == "success":
            return f"Summary from URL:\n{result['summary']}"
        else:
            return "Failed to scrape content from the URL."

    async def _handle_real_time(self, details: Dict[str, Any], agent: VoicePipelineAgent) -> str:
        """Fetch and present real-time information based on the query."""
        query = details.get("query", "")
        if not query:
            return "Please specify what real-time information you need."

        results = await real_time_search({"query": query})
        if results and results.get("data"):
            return f"Real-time info:\n{results['data'][:500]}..."
        else:
            return "Could not retrieve real-time information."

    async def _handle_todo(self, details: Dict[str, Any], agent: VoicePipelineAgent) -> str:
        """Manage a todo list based on user commands."""
        task = details.get("query", "")
        if not task:
            return "Please specify the todo task."

        result = await asyncio.to_thread(todo.TodoManager()(task))
        return f"Todo list updated: {result}"

    async def _handle_conversation(self, details: Dict[str, Any], agent: VoicePipelineAgent) -> str:
        """Handle general conversations using the LLM."""
        return None

    async def _generate_email_content(self, details: Dict[str, Any], agent: VoicePipelineAgent) -> Dict[str, str]:
        """Generate email content and subject using the LLM."""
        content = details.get("content", "")
        to_email = details.get("to", "")

        if not to_email:
            raise ValueError("Recipient email address is required.")

        email_content = await agent.llm.generate(
            f"Compose a professional email based on: {content}. "
            f"Keep it concise and under {self.config.EMAIL_CONTENT_LENGTH} characters."
        )
        subject = await agent.llm.generate(f"Subject line for: {content}")

        return {
            "to": to_email,
            "subject": subject.strip(),
            "body": email_content.strip()
        }

    def _format_search_results(self, results: Dict[str, Any]) -> str:
        """Format web search results for concise presentation."""
        if not results or results.get("status") != "success":
            return "No relevant results found."

        overview = results.get("overview", "No overview available.")
        sources = results.get("source_summaries", [])
        formatted_sources = "\n".join(sources[:self.config.MAX_SOURCES]) if sources else "No sources available."

        return f"Search Results:\n{overview}\n\nSources:\n{formatted_sources}"

def prewarm(proc: JobProcess):
    """Preload models and resources for faster task execution."""
    config = Config()
    
    # Initialize models
    try:
        if config.TRANSCRIPTION_MODEL == "groq":
            stt_model = openai.STT.with_groq(model="whisper-large-v3")
        else:
            stt_model = openai.STT(model="whisper-1")

        if config.RESPONSE_MODEL == "groq":
            llm_model = openai.LLM.with_groq(model="llama-3.3-70b-versatile")
        else:
            llm_model = openai.LLM(model="gpt-4")

        # Using Deepgram for TTS
        tts_model = deepgram.TTS()

        # Update process userdata
        proc.userdata.update({
            "vad": silero.VAD.load(),
            "task_router": TaskRouter(),
            "stt": stt_model,
            "llm": llm_model,
            "tts": tts_model
        })
    except Exception as e:
        logger.error(f"Failed to initialize models: {str(e)}")
        raise

async def entrypoint(ctx: JobContext):
    """Main entrypoint for the voice assistant."""
    config = Config()
    system_prompt = (
        "You are a helpful voice assistant created by OpenCode. "
        "Use short and long sentences, conversational responses optimized for voice interaction. "
        "Avoid markdown formatting and special characters. "
        "When handling emails: generate clear subject lines and concise body content. "
        "For web searches: summarize key points clearly. "
        "Maintain a friendly and professional tone in all interactions."
    )

    initial_ctx = llm.ChatContext().append(role="system", text=system_prompt)

    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    participant = await ctx.wait_for_participant()
    logger.info(f"starting voice assistant for participant {participant.identity}")

    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=ctx.proc.userdata["stt"],
        llm=ctx.proc.userdata["llm"],
        tts=ctx.proc.userdata["tts"],
        chat_ctx=initial_ctx,
    )

    task_router = ctx.proc.userdata["task_router"]

    async def message_handler(text: str):
        # Handle email confirmations first
        if "pending_email" in agent.context:
            confirmation = text.lower().strip()
            if "confirm" in confirmation:
                email_data = agent.context["pending_email"]
                result = await asyncio.to_thread(
                    task_router.email_service.send_email_via_assistant,
                    "user@example.com",  # Replace with actual recipient from context
                    email_data["subject"],
                    email_data["content"]
                )
                if result["status"] == "success":
                    await agent.say("Email sent successfully.")
                else:
                    await agent.say("Failed to send email. Please try again later.")
                del agent.context["pending_email"]
                return
            
            elif "cancel" in confirmation:
                await agent.say("Email cancelled.")
                del agent.context["pending_email"]
                return
            # for editing the email
            elif "edit" in confirmation:
                email_data = agent.context["pending_email"]
                email_content = await agent.llm.generate(f"Edit the email content: {email_data['content']}")
                email_subject = await agent.llm.generate(f"Edit the email subject: {email_data['subject']}")
                agent.context["pending_email"]["subject"] = email_subject.strip()
                agent.context["pending_email"]["content"] = email_content.strip()
                await agent.say("Email edited.")
                return

        # Normal task processing
        task = task_router.classify_request(text)
        response = await task_router.handle_task(task["type"], task["details"], agent)

        if response:
            try:
                await agent.say(response, allow_interruptions=True)
            except asyncio.CancelledError as e:
                logger.error(f"CancelledError in agent.say: {e}")
            except Exception as e:
                logger.error(f"Error in agent.say: {e}")
        else:
            # Fallback to LLM conversation
            await agent.process_message(text)

    agent.on_message = message_handler
    agent.start(ctx.room, participant)
    await agent.say("Hello! How can I assist you today?", allow_interruptions=True)

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )

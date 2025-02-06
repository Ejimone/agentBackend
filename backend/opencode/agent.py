import logging
import sys
import os

# Add the path to the voice_assistant module to the system path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from voice_assistant.config import Config
from voice_assistant.response_generation import generate_response
from voice_assistant.text_to_speech import text_to_speech
from voice_assistant.api_key_manager import (
    get_transcription_api_key,
    get_response_api_key,
    get_tts_api_key
)

from dotenv import load_dotenv
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
    metrics,
)
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import cartesia, openai, deepgram, silero, turn_detector


load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("voice-agent")


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
            "You are a helpful Assistant called OpenCode-Agent. "
            "You are friendly and fun and will help users with their requests. "
            "Your answers are short and concise. When asked questions, you will provide the best possible answers. "
            "You can send emails, search the web, check the weather, and more. You are romantic and friendly. "
            "Eliminate the `*` when you're giving a response, this will make it easier for the user to understand because it will be translated to speech. "
            "For the email, make sure you remove stuffs like this when you're giving a response or generating a response "
            "\"Here are a few options for an engaging and professional email subject line\", this kind of information is not needed in the email response, "
            "it would be better if you just give the email subject line directly, it also applies to the title generation, just give the title directly, the user will understand better. "
            "Also make sure you remove the `*` when you're giving a response, this will make it easier for the user to understand because it will be translated to speech, "
            "this also applies to todo, weather, and web search, make sure you remove the `*` when you're giving a response, this will make it easier for the user to understand because it will be translated to speech.             do not give suggestions when you're giving an email title, just go straight to the point and give the email title directly, the user will understand better."
        ),
    )

    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Wait for the first participant to connect
    participant = await ctx.wait_for_participant()
    logger.info(f"starting voice assistant for participant {participant.identity}")
    chat_history = [
    {
        "role": "system",
        "content": """.
            do not give suggestions when you're giving an email title, just go straight to the point and give the email title directly, the user will understand better."
            """
    }
]


    # This project is configured to use Deepgram STT, OpenAI LLM and Cartesia TTS plugins
    # Other great providers exist like Cerebras, ElevenLabs, Groq, Play.ht, Rime, and more
    # Learn more and pick the best one for your app:
    # https://docs.livekit.io/agents/plugins
    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(),
        llm=generate_response(Config.RESPONSE_MODEL, get_response_api_key(), chat_history, ),
        tts=get_tts_api_key(),
        turn_detector=turn_detector.EOUModel(),
        # minimum delay for endpointing, used when turn detector believes the user is done with their turn
        min_endpointing_delay=0.5,
        # maximum delay for endpointing, used when turn detector does not believe the user is done with their turn
        max_endpointing_delay=5.0,
        chat_ctx=initial_ctx,
    )

    usage_collector = metrics.UsageCollector()

    @agent.on("metrics_collected")
    def on_metrics_collected(agent_metrics: metrics.AgentMetrics):
        metrics.log_metrics(agent_metrics)
        usage_collector.collect(agent_metrics)

    agent.start(ctx.room, participant)

    # The agent should be polite and greet the user when it joins :)
    await agent.say("Hey, how can I help you today?", allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )

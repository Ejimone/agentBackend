import os
import json
import logging
import requests
import asyncio
from datetime import datetime
import pytz
from langchain_community.agent_toolkits.load_tools import load_tools
from langchain.agents import AgentType, initialize_agent
from langchain.memory import ConversationBufferMemory
from langchain_openai import OpenAI
from google.generativeai import GenerativeModel
from weather import get_weather
from Ai import initialize_llm
from typing import Dict, Any
logger = logging.getLogger(__name__)

async def get_current_time(location: str) -> Dict[str, Any]:
    """Get current time for a specific location"""
    try:
        # Dictionary of common US timezone mappings
        us_timezones = {
            'eastern': 'US/Eastern',
            'central': 'US/Central',
            'mountain': 'US/Mountain',
            'pacific': 'US/Pacific',
            'alaska': 'US/Alaska',
            'hawaii': 'US/Hawaii'
        }
        
        # Default to showing all major US timezones if specific zone not specified
        if location.lower() in ['us', 'usa']:
            current_times = []
            for zone_name, timezone in us_timezones.items():
                tz = pytz.timezone(timezone)
                current_time = datetime.now(tz)
                current_times.append(f"🕐 {zone_name.title()}: {current_time.strftime('%I:%M %p')}")
            
            return {
                "status": "success",
                "data": "\n".join(current_times),
                "type": "time"
            }
        else:
            # Try to find the specific timezone
            try:
                tz = pytz.timezone(location)
                current_time = datetime.now(tz)
                return {
                    "status": "success",
                    "data": f"🕐 Current time in {location}: {current_time.strftime('%I:%M %p')}",
                    "type": "time"
                }
            except pytz.exceptions.UnknownTimeZoneError:
                return {
                    "status": "error",
                    "message": f"Could not find timezone for {location}"
                }
    except Exception as e:
        logger.error(f"Error in get_current_time: {str(e)}")
        return {"status": "error", "message": str(e)}

async def real_time_search(user_prompt: str) -> Dict[str, Any]:
    """Handle real-time information requests"""
    try:
        logger.info(f"Received search query: {user_prompt}")
        gemini_model = initialize_llm()
        if not gemini_model:
            logger.error("Could not initialize Gemini model")
            return {"status": "error", "message": "Could not initialize Gemini model"}

        # Analyze the type of real-time information needed
        analysis_prompt = f"""
        Analyze this request and return a JSON response.
        Request: "{user_prompt}"

        Rules:
        1. For weather requests, extract only the city/location name
        2. For time requests, extract only the timezone/location
        3. Return valid JSON

        Return EXACTLY in this format:
        {{
            "type": "weather",
            "location": "london"
        }}

        OR

        {{
            "type": "time",
            "location": "new york"
        }}
        """
        
        response = gemini_model.generate_content(analysis_prompt)
        response_text = response.text.strip()
        
        logger.info(f"Gemini Response: {response_text}")
        
        try:
            clean_response = response_text.replace("```json", "").replace("```", "").strip()
            request_info = json.loads(clean_response)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {str(e)}")
            return {
                "status": "error",
                "message": "Failed to parse request information."
            }
        
        if not all(key in request_info for key in ["type", "location"]):
            logger.error("Missing required fields in request info")
            return {
                "status": "error",
                "message": "Could not determine request type or location."
            }
        
        # Route to appropriate handler
        if request_info["type"] == "weather":
            logger.info(f"Getting weather for location: {request_info['location']}")
            return await get_weather(request_info["location"])
        elif request_info["type"] == "time":
            logger.info(f"Getting time for location: {request_info['location']}")
            return await get_current_time(request_info["location"])
        
        logger.error(f"Unsupported request type: {request_info['type']}")
        return {
            "status": "error",
            "message": f"Unsupported request type: {request_info['type']}"
        }

    except Exception as e:
        logger.error(f"Error in real_time_search: {str(e)}")
        return {
            "status": "error",
            "message": f"Error processing request: {str(e)}"
        }
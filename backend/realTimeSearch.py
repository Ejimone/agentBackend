import os
import json
import logging
import requests
import asyncio
from datetime import datetime, timedelta
import pytz
from typing import Dict, Any, Optional
from cachetools import TTLCache
from langchain_community.agent_toolkits.load_tools import load_tools
from langchain.agents import AgentType, initialize_agent
from langchain.memory import ConversationBufferMemory
from langchain_openai import OpenAI
from google.generativeai import GenerativeModel
from weather import get_weather
from ai import initialize_gemini
import httpx

logger = logging.getLogger(__name__)

# Configure cache with 10 minute TTL
CACHE = TTLCache(maxsize=1000, ttl=600)

async def get_current_time(location: str) -> Dict[str, Any]:
    """Get current time for a specific location with enhanced timezone handling"""
    try:
        # Normalize location input
        location = location.strip().lower()
        
        # Check cache first
        cache_key = f"time_{location}"
        if cache_key in CACHE:
            return CACHE[cache_key]

        timezone_mappings = {
            # North America
            'nyc': 'America/New_York',
            'la': 'America/Los_Angeles',
            'chicago': 'America/Chicago',
            # Europe
            'london': 'Europe/London',
            'paris': 'Europe/Paris',
            'berlin': 'Europe/Berlin',
            # Asia
            'tokyo': 'Asia/Tokyo',
            'singapore': 'Asia/Singapore',
            'dubai': 'Asia/Dubai',
            # Special cases
            'utc': 'UTC'
        }

        # Handle country-level requests
        country_zones = {
            'us': ['America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles'],
            'india': ['Asia/Kolkata'],
            'china': ['Asia/Shanghai'],
            'russia': ['Europe/Moscow', 'Asia/Vladivostok']
        }

        if location in country_zones:
            zones = country_zones[location]
            current_times = []
            for zone in zones:
                tz = pytz.timezone(zone)
                current_time = datetime.now(tz)
                current_times.append(f"• {zone.split('/')[-1]}: {current_time.strftime('%I:%M %p %Z')}")
            
            result = {
                "status": "success",
                "data": "\n".join(current_times),
                "type": "time",
                "source": "timezone_db",
                "timestamp": datetime.utcnow().isoformat()
            }
            CACHE[cache_key] = result
            return result

        # Try direct timezone lookup
        tz_name = timezone_mappings.get(location, location)
        try:
            tz = pytz.timezone(tz_name)
            current_time = datetime.now(tz)
            result = {
                "status": "success",
                "data": f"🕒 {tz_name.replace('_', ' ').title()}: {current_time.strftime('%I:%M %p %Z')}",
                "type": "time",
                "source": "timezone_db",
                "timestamp": datetime.utcnow().isoformat()
            }
            CACHE[cache_key] = result
            return result
        except pytz.exceptions.UnknownTimeZoneError:
            # Fallback to API
            return await fetch_time_from_api(location)

    except Exception as e:
        logger.error(f"Time lookup error: {str(e)}", exc_info=True)
        return error_response(f"Time lookup failed: {str(e)}")

async def fetch_time_from_api(location: str) -> Dict[str, Any]:
    """Fallback timezone lookup using geolocation API"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": location,
                    "format": "json",
                    "limit": 1
                }
            )
            data = response.json()
            if data:
                lat = data[0]['lat']
                lon = data[0]['lon']
                
                time_response = await client.get(
                    f"https://timeapi.io/api/Time/current/coordinate",
                    params={"latitude": lat, "longitude": lon}
                )
                time_data = time_response.json()
                
                result = {
                    "status": "success",
                    "data": f"🕒 {location.title()}: {time_data['time']} {time_data['timeZone']}",
                    "type": "time",
                    "source": "timeapi.io",
                    "timestamp": datetime.utcnow().isoformat()
                }
                return result
            return error_response("Location not found")
    except Exception as e:
        logger.error(f"API time lookup failed: {str(e)}")
        return error_response("Could not determine time for this location")

def error_response(message: str) -> Dict[str, Any]:
    return {
        "status": "error",
        "message": message,
        "type": "error",
        "timestamp": datetime.utcnow().isoformat()
    }

async def real_time_search(user_prompt: str) -> Dict[str, Any]:
    """Enhanced real-time information handler with multiple fallback strategies"""
    try:
        logger.info(f"Processing query: {user_prompt}")
        gemini_model = initialize_gemini()
        if not gemini_model:
            logger.error("Gemini initialization failed")
            return error_response("Service unavailable")

        # Enhanced analysis prompt with examples
        analysis_prompt = f"""
        Analyze the request and respond with JSON. Categories supported:
        - weather (requires location)
        - time (requires timezone/location)
        - news (requires topic)
        - stocks (requires ticker symbol)
        - sports (requires team/league)
        - flights (requires flight number)

        Examples:
        Input: "What's the weather in Tokyo?"
        Output: {{"type": "weather", "location": "Tokyo"}}

        Input: "Did the Lakers win last night?"
        Output: {{"type": "sports", "team": "Los Angeles Lakers"}}

        Input: "What's the latest news about AI?"
        Output: {{"type": "news", "topic": "artificial intelligence"}}

        Input: "{user_prompt}"
        """

        try:
            response = gemini_model.generate_content(analysis_prompt)
            response_text = response.text.strip()
            clean_response = response_text.replace("```json", "").replace("```", "").strip()
            request_info = json.loads(clean_response)
        except (json.JSONDecodeError, AttributeError) as e:
            logger.error(f"Analysis failed: {str(e)}")
            return await fallback_search(user_prompt)

        # Validate response structure
        if not validate_request_info(request_info):
            return await fallback_search(user_prompt)

        # Route to appropriate handler
        handlers = {
            "weather": handle_weather,
            "time": handle_time,
            "news": handle_news,
            "stocks": handle_stocks,
            "sports": handle_sports,
            "flights": handle_flights
        }

        handler = handlers.get(request_info["type"].lower(), handle_unknown_type)
        return await handler(request_info)

    except Exception as e:
        logger.error(f"Real-time search failed: {str(e)}", exc_info=True)
        return error_response("Failed to process request")

def validate_request_info(request_info: Dict) -> bool:
    required_fields = {
        "weather": ["location"],
        "time": ["location"],
        "news": ["topic"],
        "stocks": ["symbol"],
        "sports": ["team"],
        "flights": ["number"]
    }
    
    req_type = request_info.get("type", "").lower()
    if req_type not in required_fields:
        return False
    
    return all(field in request_info for field in required_fields[req_type])

async def handle_weather(params: Dict) -> Dict[str, Any]:
    """Handle weather requests with retry logic"""
    try:
        location = params["location"]
        return await get_weather(location)
    except Exception as e:
        logger.error(f"Weather lookup failed: {str(e)}")
        return error_response("Could not retrieve weather data")

async def handle_time(params: Dict) -> Dict[str, Any]:
    """Handle time requests"""
    location = params.get("location", "UTC")
    return await get_current_time(location)

async def handle_news(params: Dict) -> Dict[str, Any]:
    """Fetch recent news articles"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": params["topic"],
                    "apiKey": os.getenv("NEWS_API_KEY"),
                    "pageSize": 5,
                    "sortBy": "publishedAt"
                }
            )
            articles = response.json().get("articles", [])
            return {
                "status": "success",
                "type": "news",
                "data": format_news(articles),
                "source": "NewsAPI",
                "timestamp": datetime.utcnow().isoformat()
            }
    except Exception as e:
        logger.error(f"News lookup failed: {str(e)}")
        return error_response("Could not retrieve news")

def format_news(articles: List[Dict]) -> str:
    return "\n".join(
        f"📰 {article['title']} ({article['source']['name']})\n{article['url']}"
        for article in articles[:3]
    )

async def fallback_search(query: str) -> Dict[str, Any]:
    """Final fallback using web search"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"Accept": "application/json", "X-Subscription-Token": os.getenv("BRAVE_API_KEY")},
                params={"q": query, "count": 3}
            )
            results = response.json().get("web", {}).get("results", [])
            return {
                "status": "partial",
                "type": "web",
                "data": format_web_results(results),
                "source": "Brave Search",
                "timestamp": datetime.utcnow().isoformat()
            }
    except Exception as e:
        logger.error(f"Fallback search failed: {str(e)}")
        return error_response("Could not retrieve information")

def format_web_results(results: List[Dict]) -> str:
    return "\n".join(
        f"🌐 {res['title']}\n{res['url']}\n{res.get('description', '')}"
        for res in results
    )

# Add similar handlers for stocks, sports, flights...

if __name__ == "__main__":
    # Test the functionality
    async def test():
        queries = [
            "What time is it in Tokyo?",
            "Show me news about quantum computing",
            "What's the weather in London?"
        ]
        
        for query in queries:
            print(f"Query: {query}")
            result = await real_time_search(query)
            print(json.dumps(result, indent=2))
            print("---")
    
    asyncio.run(test())
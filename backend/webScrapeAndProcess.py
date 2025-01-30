import os
import re
import asyncio
import random  # Add this import
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass
import logging
from dotenv import load_dotenv
import requests
from urllib.parse import quote_plus

# Third-party imports
from bs4 import BeautifulSoup
import aiohttp
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception_type,
    wait_exponential
)
from google.api_core.exceptions import GoogleAPIError
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Validate required environment variables
def validate_env_vars():
    required_vars = ["SERPAPI_API_KEY", "GEMINI_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")

logger = logging.getLogger(__name__)

# Configuration
@dataclass(frozen=True)
class ScraperConfig:
    """Immutable scraper configuration parameters"""
    MAX_RETRIES: int = 3
    REQUEST_TIMEOUT: int = 15
    MAX_CONTENT_LENGTH: int = 100000  # 100KB
    MAX_SUMMARY_TOKENS: int = 10000
    SEARCH_RESULTS_LIMIT: int = 5
    USER_AGENTS: Tuple[str] = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
        '(KHTML, like Gecko) Version/14.1.1 Safari/605.1.15'
    )
    BLACKLIST_DOMAINS: Tuple[str] = ('malicious.com', 'spam.org')

class ScraperError(Exception):
    """Base exception for scraping errors"""
    pass

class ContentTooLargeError(ScraperError):
    """Exception raised when content exceeds size limits"""
    pass

class WebScraper:
    """Production-grade web scraping and processing service"""
    
    def __init__(self, config: ScraperConfig = ScraperConfig()):
        self.config = config
        self.session = aiohttp.ClientSession()
        self.gemini_model = self._initialize_gemini()

    def _initialize_gemini(self) -> genai.GenerativeModel:
        """Initialize Gemini model with validation"""
        try:
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            return genai.GenerativeModel('gemini-pro')
        except Exception as e:
            logger.error("Failed to initialize Gemini model: %s", e)
            raise ScraperError("Gemini initialization failed") from e

    async def close(self) -> None:
        """Cleanup resources"""
        await self.session.close()

    @retry(
        stop=stop_after_attempt(ScraperConfig.MAX_RETRIES),
        wait=wait_random_exponential(multiplier=1, max=10)
    )
    async def _fetch_url(self, url: str) -> str:
        """Fetch URL content with retry logic and security checks"""
        self._validate_url(url)
        
        try:
            headers = {'User-Agent': self._random_user_agent()}
            async with self.session.get(
                url,
                headers=headers,
                timeout=self.config.REQUEST_TIMEOUT,
                ssl=False
            ) as response:
                response.raise_for_status()
                content = await response.text()
                
                if len(content) > self.config.MAX_CONTENT_LENGTH:
                    raise ContentTooLargeError(
                        f"Content exceeds {self.config.MAX_CONTENT_LENGTH} bytes limit"
                    )
                
                return content
        except aiohttp.ClientError as e:
            logger.error("Network error fetching %s: %s", url, e)
            raise ScraperError(f"Failed to fetch {url}") from e

    def _random_user_agent(self) -> str:
        """Get random user agent from configured list"""
        return random.choice(self.config.USER_AGENTS)

    def _validate_url(self, url: str) -> None:
        """Validate URL against security rules"""
        if any(domain in url for domain in self.config.BLACKLIST_DOMAINS):
            raise ScraperError(f"Blocked domain in URL: {url}")
        
        if not re.match(r'^https?://', url, re.IGNORECASE):
            raise ScraperError(f"Invalid URL protocol: {url}")

    async def scrape_url(self, url: str) -> str:
        """Scrape and sanitize content from URL"""
        try:
            content = await self._fetch_url(url)
            soup = BeautifulSoup(content, 'html.parser')
            
            # Remove unnecessary elements
            for tag in ['script', 'style', 'nav', 'footer', 'iframe', 'noscript']:
                for element in soup(tag):
                    element.decompose()
            
            # Content extraction strategy
            main_content = self._extract_main_content(soup)
            return self._clean_content(main_content)
        except Exception as e:
            logger.error("Error scraping %s: %s", url, e)
            raise

    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        """Extract main content using multiple strategies"""
        selectors = [
            {'name': 'article'},
            {'attrs': {'role': 'main'}},
            {'class': re.compile(r'(content|article|post|entry)')}
        ]
        
        for selector in selectors:
            elements = soup.find_all(**selector)
            if elements:
                return ' '.join(e.get_text() for e in elements[:3])
        
        # Fallback to paragraph aggregation
        paragraphs = soup.find_all('p')
        return ' '.join(p.get_text() for p in paragraphs) if paragraphs else ''

    def _clean_content(self, content: str) -> str:
        """Clean and normalize scraped content"""
        cleaned = re.sub(r'\s+', ' ', content)
        return cleaned.strip()

    @retry(
        stop=stop_after_attempt(ScraperConfig.MAX_RETRIES),
        retry=retry_if_exception_type(GoogleAPIError)
    )
    async def summarize_content(self, content: str) -> str:
        """Generate AI summary with proper chunking"""
        try:
            chunks = self._chunk_content(content)
            summaries = []
            
            for chunk in chunks:
                response = await asyncio.to_thread(
                    self.gemini_model.generate_content,
                    self._summary_prompt(chunk)
                )
                summaries.append(response.text)
            
            return '\n\n'.join(summaries)
        except GoogleAPIError as e:
            logger.error("Gemini API error: %s", e)
            raise ScraperError("Summary generation failed") from e

    def _chunk_content(self, content: str) -> List[str]:
        """Split content into manageable chunks"""
        words = content.split()
        return [
            ' '.join(words[i:i+self.config.MAX_SUMMARY_TOKENS]) 
            for i in range(0, len(words), self.config.MAX_SUMMARY_TOKENS)
        ]

    def _summary_prompt(self, chunk: str) -> str:
        """Generate structured summary prompt"""
        return f"""
        Analyze and summarize this content chunk:
        {chunk}
        
        Include:
        - Key concepts and entities
        - Relationships between ideas
        - Important quantitative data
        - Contextual significance
        
        Format using markdown with clear section headings.
        """

    async def web_search(self, query: str) -> Dict[str, Any]:
        """Perform complete search and analysis workflow"""
        try:
            search_results = await self._serpapi_search(query)
            processed = await asyncio.gather(*[
                self._process_result(result)
                for result in search_results[:3]
            ])
            
            valid_results = [p for p in processed if p]
            overview = await self._generate_overview(query, valid_results)
            
            return {
                'status': 'success',
                'data': self._format_output(query, overview, valid_results)
            }
        except Exception as e:
            logger.error("Search failed for %s: %s", query, e)
            return {
                'status': 'error',
                'message': f"Search failed: {str(e)}"
            }

    async def _serpapi_search(self, query: str) -> List[Dict]:
        """Execute SerpAPI search with validation"""
        params = {
            'api_key': os.getenv("SERPAPI_API_KEY"),
            'engine': 'google',
            'q': query,
            'num': self.config.SEARCH_RESULTS_LIMIT,
            'gl': 'us'
        }
        
        try:
            async with self.session.get(
                "https://serpapi.com/search",
                params=params,
                timeout=self.config.REQUEST_TIMEOUT
            ) as response:
                data = await response.json()
                return data.get('organic_results', [])
        except Exception as e:
            logger.error("SerpAPI search failed: %s", e)
            raise ScraperError("Search API unavailable") from e

    async def _process_result(self, result: Dict) -> Optional[Dict]:
        """Process individual search result"""
        try:
            url = result.get('link', '')
            content = await self.scrape_url(url)
            summary = await self.summarize_content(content)
            
            return {
                'title': result.get('title', 'No Title'),
                'url': url,
                'summary': summary,
                'snippet': result.get('snippet', '')
            }
        except Exception as e:
            logger.warning("Skipping invalid result: %s", e)
            return None

    async def _generate_overview(self, query: str, results: List[Dict]) -> str:
        """Generate comprehensive overview from results"""
        context = "\n".join([r['summary'] for r in results])
        prompt = f"""
        Synthesize a comprehensive report on {query} using these sources:
        {context}
        
        Structure with:
        1. Executive Summary
        2. Key Findings
        3. Comparative Analysis
        4. Critical Evaluation
        5. Future Implications
        
        Include references to sources where applicable.
        """
        
        response = await asyncio.to_thread(
            self.gemini_model.generate_content,
            prompt
        )
        return response.text

    def _format_output(self, query: str, overview: str, results: List[Dict]) -> str:
        """Format final output with proper structure"""
        return f"""
        # Comprehensive Analysis: {query}
        
        ## Overview
        {overview}
        
        ## Source Summaries
        {self._format_source_summaries(results)}
        """

    def _format_source_summaries(self, results: List[Dict]) -> str:
        """Format individual source summaries"""
        return "\n\n".join(
            f"### {idx+1}. {res['title']}\n"
            f"**URL**: {res['url']}\n"
            f"{res['summary']}\n"
            for idx, res in enumerate(results)
        )

@retry(
    wait=wait_exponential(multiplier=1, min=4, max=10),
    stop=stop_after_attempt(3)
)
def web_search(query: str) -> Union[str, List[str]]:
    """
    Perform a web search and return results
    """
    try:
        # Implement your web search logic here
        # This is a simplified example
        results = ["Web search results for: " + query]
        return results
    except Exception as e:
        logger.error(f"Error in web search: {str(e)}")
        return f"Error performing web search: {str(e)}"

def scrape_and_summarize(url: str) -> str:
    """
    Scrape content from a URL and summarize it
    """
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        # Add your scraping and summarizing logic here
        return "Content summary"
    except Exception as e:
        logger.error(f"Error in scraping: {str(e)}")
        return f"Error scraping content: {str(e)}"

# Usage example
async def scrape_and_summarize():
    scraper = WebScraper()
    try:
        # Validate environment variables before proceeding
        validate_env_vars()
        
        result = await scraper.web_search("Climate change impacts 2023")
        if result['status'] == 'success':
            print(result['data'])
        else:
            print(f"Error: {result.get('message', 'Unknown error')}")
    except Exception as e:
        print(f"Error during execution: {str(e)}")
    finally:
        await scraper.close()

if __name__ == "__main__":
    asyncio.run(scrape_and_summarize())
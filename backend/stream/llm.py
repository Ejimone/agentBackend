# chatbot.py
import os
import logging
from typing import Optional
import openai
import google.generativeai as genai

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DualAIChatBot:
    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        model_preference: str = "openai"
    ):
        """
        Initialize chatbot with both API providers
        
        Args:
            openai_api_key: Optional OpenAI API key (default from environment)
            gemini_api_key: Optional Gemini API key (default from environment)
            model_preference: Preferred provider ("openai" or "gemini")
        """
        # Configure APIs
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.model_preference = model_preference.lower()
        
        # Validate API keys
        if not self.openai_api_key and not self.gemini_api_key:
            raise ValueError("At least one API key must be provided")
            
        # Initialize clients
        if self.openai_api_key:
            openai.api_key = self.openai_api_key
            
        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)
            self.gemini_model = genai.GenerativeModel('gemini-pro')

        # Track API status
        self.openai_available = bool(self.openai_api_key)
        self.gemini_available = bool(self.gemini_api_key)

    def generate_response(
        self,
        prompt: str,
        max_retries: int = 1,
        **kwargs
    ) -> str:
        """
        Generate response with automatic fallback
        
        Args:
            prompt: User input prompt
            max_retries: Number of retries per API
            **kwargs: Additional model parameters
            
        Returns:
            Generated response text
        """
        try:
            if self.model_preference == "openai" and self.openai_available:
                return self._try_openai(prompt, max_retries, **kwargs)
            elif self.model_preference == "gemini" and self.gemini_available:
                return self._try_gemini(prompt, max_retries, **kwargs)
            else:
                return self._fallback_strategy(prompt, max_retries, **kwargs)
        except Exception as e:
            logger.error(f"All APIs failed: {str(e)}")
            return "Sorry, I'm currently unable to process requests. Please try again later."

    def _try_openai(self, prompt: str, retries: int, **kwargs) -> str:
        """Attempt OpenAI request with retries"""
        for attempt in range(retries + 1):
            try:
                response = openai.ChatCompletion.create(
                    model=kwargs.get("model", "gpt-3.5-turbo"),
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=kwargs.get("max_tokens", 1000),
                    temperature=kwargs.get("temperature", 0.7),
                    timeout=10  # Seconds
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"OpenAI attempt {attempt + 1} failed: {str(e)}")
                if attempt == retries:
                    self.openai_available = False
                    logger.error("Marking OpenAI as unavailable")
                    return self._try_gemini(prompt, retries, **kwargs)

    def _try_gemini(self, prompt: str, retries: int, **kwargs) -> str:
        """Attempt Gemini request with retries"""
        for attempt in range(retries + 1):
            try:
                response = self.gemini_model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=kwargs.get("max_tokens", 1000),
                        temperature=kwargs.get("temperature", 0.7)
                    )
                )
                return response.text.strip()
            except Exception as e:
                logger.warning(f"Gemini attempt {attempt + 1} failed: {str(e)}")
                if attempt == retries:
                    self.gemini_available = False
                    logger.error("Marking Gemini as unavailable")
                    return self._try_openai(prompt, retries, **kwargs)

    def _fallback_strategy(self, prompt: str, retries: int, **kwargs) -> str:
        """Handle fallback between available APIs"""
        if self.openai_available:
            return self._try_openai(prompt, retries, **kwargs)
        if self.gemini_available:
            return self._try_gemini(prompt, retries, **kwargs)
        raise RuntimeError("No available API providers")

    def get_available_providers(self) -> list:
        """Return list of currently available providers"""
        available = []
        if self.openai_available:
            available.append("openai")
        if self.gemini_available:
            available.append("gemini")
        return available
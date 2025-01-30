import os
import logging
from typing import Any, Dict, Optional, Tuple
from dotenv import load_dotenv

# LangChain imports
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_openai import OpenAI

# Google imports
import google.generativeai as genai
from google.generativeai import GenerativeModel

# Initialize logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class LLMInitializer:
    """Handles initialization of different LLM providers with proper error handling"""
    
    @staticmethod
    def initialize_openai() -> Tuple[Optional[OpenAI], bool]:
        """Initialize OpenAI client with environment verification"""
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            logger.warning("OPENAI_API_KEY environment variable not set")
            return None, False

        try:
            llm = OpenAI(
                temperature=0.7,
                openai_api_key=openai_api_key,
                verbose=True
            )
            # Simple validation query
            llm.invoke("connection test")
            return llm, True
        except Exception as e:
            logger.error(f"OpenAI initialization failed: {str(e)}")
            return None, False

    @staticmethod
    def initialize_gemini() -> Optional[GenerativeModel]:
        """Initialize Google Gemini model with proper configuration"""
        try:
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            return genai.GenerativeModel('gemini-pro')
        except Exception as e:
            logger.error(f"Gemini initialization failed: {str(e)}")
            return None


class ChainCreator:
    """Creates and configures conversation chains for different LLM providers"""
    
    PROMPT_TEMPLATE = PromptTemplate(
        input_variables=["user_input"],
        template="""You are a helpful AI assistant. Respond to the following:

User: {user_input}
Assistant:"""
    )

    def __init__(self):
        self.memory = ConversationBufferMemory()
        self.llm_initializer = LLMInitializer()

    def create_chain(self, use_gemini: bool = False) -> LLMChain:
        """
        Create conversation chain with fallback logic
        
        Args:
            use_gemini: Force use of Gemini instead of OpenAI
            
        Returns:
            Configured LLMChain instance
            
        Raises:
            RuntimeError: If no working LLM provider is found
        """
        if not use_gemini:
            llm, success = self.llm_initializer.initialize_openai()
            if success and llm:
                return LLMChain(
                    llm=llm,
                    prompt=self.PROMPT_TEMPLATE,
                    memory=self.memory,
                    verbose=True
                )

        gemini_model = self.llm_initializer.initialize_gemini()
        if gemini_model:
            return self._create_gemini_chain(gemini_model)

        raise RuntimeError("No working LLM provider available")

    def _create_gemini_chain(self, model: GenerativeModel) -> LLMChain:
        """Create custom chain wrapper for Gemini models"""
        class GeminiChainWrapper(LLMChain):
            """Custom chain implementation for Gemini API"""
            
            def _call(self, inputs: Dict[str, Any], **kwargs) -> Dict[str, str]:
                formatted_prompt = self.prompt.format(**inputs)
                response = model.generate_content(formatted_prompt)
                return {'text': response.text}

        return GeminiChainWrapper(
            prompt=self.PROMPT_TEMPLATE,
            memory=self.memory,
            verbose=True
        )


def interactive_chat():
    """Run interactive chat session with the AI"""
    load_dotenv()
    chain_creator = ChainCreator()
    
    try:
        agent_chain = chain_creator.create_chain()
        print("AI Assistant ready! Type 'quit' to exit.")
        
        while True:
            user_input = input("\nYou: ").strip()
            if user_input.lower() == 'quit':
                break
                
            try:
                response = agent_chain.run(user_input=user_input)
                print("\nAI:", response.strip())
            except Exception as e:
                logger.error(f"Error during chat: {e}")
                print("\nAI: Sorry, I encountered an error. Please try again.")
                
    except RuntimeError as e:
        logger.error(str(e))
        print("Failed to initialize AI. Please check your API keys.")

if __name__ == "__main__":
    interactive_chat()
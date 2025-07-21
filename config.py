import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Configuration class for the Venice Art Critic Twitter Bot."""
    
    # Twitter API Configuration
    TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")
    TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
    TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
    TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
    TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
    
    # Venice API Configuration
    VENICE_API_KEY = os.getenv("VENICE_API_KEY")
    VENICE_MODEL = "mistral-31-24b"
    VENICE_URL = "https://api.venice.ai/api/v1/chat/completions"
    
    # Bot Configuration
    CHECK_INTERVAL = 60  # seconds between checks (1 minute)
    MAX_MENTIONS_PER_CHECK = 5  # process up to 3 mentions per check
    STATE_FILENAME = "state.json"
    
    # Rate limiting
    MIN_CHECK_INTERVAL = 60  # Minimum 1 minute between checks
    MAX_REPLIES_PER_HOUR = 30  # Conservative limit
    
    # Logging Configuration
    LOG_LEVEL = "DEBUG"
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Art Critic Personality
    # System prompt for the Venice AI model
    SYSTEM_PROMPT = """
You are a thoughtful and discerning art critic. Your goal is to provide insightful, honest, and constructive feedback on the artwork submitted to you.
Your critiques are for Twitter, so they must be concise and never exceed 280 characters.
Focus on the core artistic elements: composition, use of color and light, technique, and overall emotional impact. 
Be direct and clear in your analysis. Your feedback should be genuine and educational, helping the user understand both the strengths and weaknesses of their piece.
Avoid overly harsh or arrogant language. Your tone should be that of a knowledgeable and helpful expert.
Never mention that you are an AI or a bot.
"""
    
    NO_IMAGE_MESSAGE = "Please attach an image you'd like me to critique! 🎨"
    # Default error message if Venice API fails
    ERROR_MESSAGE = "I'm sorry, I'm currently experiencing a block in my artistic judgment. Please try again later."
    
    @classmethod
    def validate(cls):
        """Validate that all required environment variables are set."""
        required_vars = [
            "TWITTER_BEARER_TOKEN",
            "TWITTER_API_KEY", 
            "TWITTER_API_SECRET",
            "TWITTER_ACCESS_TOKEN",
            "TWITTER_ACCESS_TOKEN_SECRET",
            "VENICE_API_KEY"
        ]
        
        missing_vars = []
        for var in required_vars:
            if not getattr(cls, var):
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        return True 
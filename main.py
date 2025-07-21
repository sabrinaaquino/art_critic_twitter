import logging
from bot import ArtCriticBot
from config import Config

# Set up logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format=Config.LOG_FORMAT
)

def main():
    """Main entry point for the Venice Art Critic Twitter Bot."""
    try:
        bot = ArtCriticBot()
        bot.run()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main() 
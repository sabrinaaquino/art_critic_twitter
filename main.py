import logging
from config import Config
from bot import VeniceBot

def setup_logging():
    """Sets up centralized logging."""
    # Set up logging
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL),
        format=Config.LOG_FORMAT
    )

def main():
    """Main entry point for the bot."""
    setup_logging()
    
    try:
        Config.validate()
        bot = VeniceBot()
        bot.run()
    except ValueError as e:
        logging.critical(f"Configuration error: {e}")
    except Exception as e:
        logging.critical(f"An unexpected error occurred: {e}", exc_info=True)

if __name__ == "__main__":
    main() 
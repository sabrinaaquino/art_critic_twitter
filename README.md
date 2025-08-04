# Venice X Bot

This is an unbiased Python-based Twitter bot that uses the Venice AI API to provide intelligent, context-aware replies to user mentions. It can analyze both text and images, understands conversational context, and leverages a three-step AI process to deliver high-quality, educational responses.

The bot is designed to be robust, with proper error handling, rate-limiting, conversation intelligence, and state management to ensure it runs smoothly and respectfully on the Twitter platform.

## Core Features

-   **Context-Aware Replies:** The bot intelligently detects conversation flow, fetches parent tweets for context, and distinguishes between new conversations and threaded replies.
-   **Three-Step AI Analysis:** For every query, the bot uses a sophisticated three-call process:
    1.  **Expert Analysis:** Sends the query to a web-enabled model for comprehensive analysis with current information.
    2.  **Content Summarization:** Distills key facts and findings from the detailed analysis.
    3.  **Tweet Crafting:** Formats the final response with automatic validation against robotic phrases.
-   **Smart Model Selection:** Uses `llama-3.3-70b` for web-enabled text, `mistral-31-24b` for images, and `venice-uncensored` for processing.
-   **Uncensored Educational Approach:** Provides comprehensive information on controversial topics while declining only harassment, doxxing, threats, and spam.
-   **Web-Enabled Intelligence:** Uses Venice's native web search for real-time information and fact-checking without knowledge cutoff mentions.
-   **Natural Communication:** No robotic greetings, direct language, and technical responses without moral advice.

## Project Structure

The project is organized into a modular structure for clarity and maintainability:

```
/venice-x-bot
|-- main.py                 # Main entry point to run the bot
|-- bot.py                  # Core bot logic and event loop
|-- config.py               # All configuration, API keys, and prompts
|-- state.py                # Handles state management (processed tweets)
|-- clients.py              # Initializes the Twitter API client
|-- twitter_client.py       # Functions for interacting with the Twitter API
|-- venice_api.py           # Functions for interacting with the Venice AI API
|-- image_processor.py      # Handles downloading and processing images
|-- requirements.txt        # Python dependencies
|-- env_example.txt         # Example file for environment variables
|-- README.md               # This file
```

## Setup & Installation

1.  **Clone the Repository:**
    ```bash
    git clone <your-repo-url>
    cd venice-x-bot
    ```

2.  **Create a Virtual Environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**
    -   Rename `env_example.txt` to `.env`.
    -   Open the `.env` file and fill in your API keys and tokens from the [Twitter Developer Portal](https://developer.twitter.com/en/portal/dashboard) and [Venice AI](https://www.venice.ai/).

## How to Run the Bot

With your environment configured, simply run the `main.py` file:

```bash
python main.py
```

The bot will initialize and start monitoring for new mentions. To stop the bot, press `Ctrl+C`. 
# Venice X Bot

A Python-based Twitter bot powered by Venice AI that provides intelligent, uncensored, and current responses to user mentions. The bot uses real-time web search and a sophisticated three-step AI pipeline to deliver accurate information on any topic.

## Key Features

- **Real-Time Web Search:** Uses Venice's native web search capabilities for current information and events
- **Three-Step AI Pipeline:** Expert Analysis → Summarization → Tweet Crafting for optimal responses
- **Uncensored Output:** Maintains direct, unfiltered communication using Venice's uncensored models
- **Smart Context Handling:** Distinguishes between new conversations and threaded replies
- **Current Information:** Only processes tweets less than 24 hours old to ensure relevance
- **Robust Error Handling:** Automatic fallback models and comprehensive error recovery

## Architecture

### AI Pipeline
1. **Expert Analysis** (`qwen3-235b`): Web-enabled analysis with real-time search
2. **Summarization** (`venice-uncensored`): Extracts key points while preserving uncensored tone
3. **Tweet Crafting** (`venice-uncensored`): Formats final response under 280 characters

### Model Configuration
- **Web Search Model:** `qwen3-235b` - Best balance of reasoning, web search, and cost
- **Vision Model:** `mistral-31-24b` - Handles images and visual content
- **Uncensored Processing:** `venice-uncensored` with `dolphin-2.9.2-qwen2-72b` fallback

### Smart Features
- **Context Filtering:** Automatically bypasses outdated context to prioritize fresh web search
- **Conversation Intelligence:** Handles both new mentions and threaded conversations
- **Rate Limiting:** Respects Twitter API limits and processes up to 5 mentions per check
- **State Management:** Tracks processed tweets to avoid duplicates

## Project Structure

```
/venice-x-bot
|-- main.py                 # Main entry point
|-- bot.py                  # Core bot logic and AI pipeline
|-- config.py               # Configuration, models, and AI prompts
|-- state.py                # State management for processed tweets
|-- clients.py              # Twitter API client initialization
|-- twitter_client.py       # Twitter API interaction functions
|-- venice_api.py           # Venice AI API integration
|-- image_processor.py      # Image download and processing
|-- test_web_search.py      # Standalone testing for the AI pipeline
|-- requirements.txt        # Python dependencies
|-- env_example.txt         # Environment variables template
```

## Setup & Installation

1. **Clone the Repository:**
   ```bash
   git clone <your-repo-url>
   cd venice-x-bot
   ```

2. **Create Virtual Environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment:**
   - Copy `env_example.txt` to `.env`
   - Add your API keys from [Twitter Developer Portal](https://developer.twitter.com/en/portal/dashboard) and [Venice AI](https://www.venice.ai/)

## Usage

### Run the Bot
```bash
python main.py
```

### Test the Pipeline
Test the AI pipeline in isolation:
```bash
python test_web_search.py
```

## Configuration

Key settings in `config.py`:
- `MAX_TWEET_AGE_HOURS = 24` - Only reply to recent tweets
- `MAX_MENTIONS_PER_CHECK = 5` - Process up to 5 mentions per cycle
- `CHECK_INTERVAL = 60` - Check for new mentions every 60 seconds
- `MAX_REPLIES_PER_HOUR = 30` - Conservative rate limiting

## AI Prompts

The bot uses carefully crafted system prompts to ensure:
- **Accuracy:** Leverages web search results for current information
- **Honesty:** Acknowledges limitations when information is insufficient
- **Focus:** Stays on-topic without tangential information
- **Directness:** Provides information without redirecting to external sources
- **Uncensored Output:** Maintains authentic, unfiltered responses

## Error Handling

- **Fallback Models:** Automatic switching to backup models on 500 errors
- **Context Filtering:** Bypasses outdated context that might interfere with current information
- **Graceful Degradation:** Continues operation even when individual components fail
- **Comprehensive Logging:** Tracks all operations for debugging and monitoring

## Rate Limiting & Safety

- Respects Twitter API rate limits
- Processes tweets sequentially with configurable delays
- Only replies to tweets less than 24 hours old
- Tracks processed tweets to avoid duplicate responses
- Conservative reply limits to maintain good standing 
# Venice X Bot (@venice_mind)

A Python-based Twitter bot powered by Venice AI that provides intelligent, uncensored, and current responses to user mentions. The bot uses real-time web search and a streamlined two-step AI pipeline to deliver accurate information on any topic.

## Key Features

- **Real-Time Web Search:** Uses Venice's native web search capabilities for current information and events
- **Streamlined AI Pipeline:** Expert Analysis → Tweet Crafting for optimal efficiency and cost
- **Uncensored Output:** Maintains direct, unfiltered communication using Venice's uncensored models (2.20% refusal rate)
- **Vision Capabilities:** Analyzes images and visual content using Mistral vision models
- **Smart Context Handling:** Distinguishes between new conversations and threaded replies
- **URL Processing:** Extracts and analyzes linked articles for comprehensive responses
- **X Premium Support:** Configurable character limits for standard (280) and premium (25,000) accounts
- **Current Information:** Only processes tweets from the last 60 minutes to ensure relevance
- **Robust Error Handling:** Automatic fallback models and comprehensive error recovery

## Architecture

### AI Pipeline (Simplified 2-Step Process)
1. **Expert Analysis**: Uses appropriate Venice model with real-time web search to generate focused, tweet-ready responses
2. **Tweet Crafting**: Refines and formats the final response with strict style guidelines and character limits

### Model Configuration
- **Text Tweets:** `venice-uncensored` - Primary uncensored model with web search for text-only content
- **Image Tweets:** `mistral-31-24b` - Vision-enabled model with web search for tweets with images
- **Backup Model:** `qwen3-235b` - Fallback model for web search if needed

### Smart Features
- **Context Intelligence:** Handles both new mentions and threaded conversations with conversation tracking
- **Image Processing:** Downloads and analyzes images from tweets automatically
- **URL Extraction:** Fetches and processes linked articles for comprehensive context
- **Rate Limiting:** Respects Twitter API limits and processes up to 5 mentions per check
- **State Management:** Tracks processed tweets and conversation threads to avoid duplicates
- **Session Filtering:** Optionally ignores mentions created before bot startup

## Project Structure

```
/venice-x-bot
|-- main.py                 # Main entry point
|-- bot.py                  # Core bot logic and AI pipeline
|-- config.py               # Configuration, models, and AI prompts
|-- state.py                # State management for processed tweets and conversations
|-- clients.py              # Twitter API client initialization
|-- twitter_client.py       # Twitter API interaction functions
|-- venice_api.py           # Venice AI API integration (2-step pipeline)
|-- image_processor.py      # Image download and processing
|-- utils.py                # URL extraction and utility functions
|-- reply_to_tweet.py       # Standalone testing script
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
   - Optionally set `X_PREMIUM_ENABLED=true` if using X Premium account

## Usage

### Run the Bot
```bash
python main.py
```

### Test Individual Tweets
Test the AI pipeline with specific tweet IDs:
```bash
python reply_to_tweet.py <tweet_id>
```

## Configuration

Key settings in `config.py`:
- `MAX_TWEET_AGE_MINUTES = 60` - Only reply to tweets from the last 60 minutes
- `MAX_MENTIONS_PER_CHECK = 5` - Process up to 5 mentions per cycle
- `CHECK_INTERVAL = 60` - Check for new mentions every 60 seconds
- `MAX_REPLIES_PER_HOUR = 30` - Conservative rate limiting
- `X_PREMIUM_ENABLED` - Enable 25,000 character limit for X Premium accounts

## Bot Identity (@venice_mind)

The bot operates as **@venice_mind** with the following characteristics:
- **Purpose:** Provide intelligent, uncensored, and current responses to user mentions
- **Personality:** Direct, honest, conversational - like a knowledgeable friend without greetings or pleasantries
- **Capabilities:** Real-time web search, image analysis, technical explanations, current events analysis
- **Unique Features:** Uncensored output, real-time information, context-aware conversations

## AI Pipeline Details

### Expert Analysis Step
- Uses `venice-uncensored` for text tweets or `mistral-31-24b` for image tweets
- Includes real-time web search results for current information
- Processes URLs and extracts article content when available
- Generates focused, tweet-ready responses with proper formatting

### Tweet Crafting Step
- Refines the expert analysis into final tweet format
- Enforces character limits (280 for standard, 25,000 for premium)
- Removes banned phrases and ensures style compliance
- Maintains uncensored, direct communication style

## Venice AI Integration

The bot leverages Venice AI's unique features:
- **Privacy-First:** No data storage or conversation logging
- **Uncensored Models:** 2.20% refusal rate vs 71% for Claude, 64% for GPT-4
- **Web Search:** Real-time information retrieval for current events
- **Vision Capabilities:** Image analysis using Mistral models
- **Multiple Models:** Automatic selection based on content type

## Error Handling & Safety

- **Graceful Degradation:** Continues operation even when individual components fail
- **Rate Limit Respect:** Honors Twitter API limits with exponential backoff
- **Conversation Tracking:** Maintains thread integrity and prevents spam
- **Age Filtering:** Only processes recent tweets to avoid stale conversations
- **Comprehensive Logging:** Tracks all operations for debugging and monitoring

## Rate Limiting & Compliance

- Respects Twitter API rate limits with intelligent backoff
- Processes tweets sequentially with configurable delays
- Only replies to tweets less than 60 minutes old
- Tracks processed tweets to avoid duplicate responses
- Conservative reply limits (30/hour) to maintain good standing
- Enforces single-author conversations to prevent thread hijacking 
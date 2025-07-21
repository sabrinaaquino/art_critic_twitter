# Venice Art Critic Twitter Bot

A modular Twitter bot that critiques artwork using the Venice AI API. The bot monitors mentions and responds with art critiques when users share images.

## Features

- **Modular Architecture**: Clean separation of concerns with dedicated modules
- **State Management**: Tracks processed tweets to avoid duplicates
- **Configurable**: Easy to customize behavior through configuration
- **Robust Error Handling**: Graceful handling of API errors and network issues
- **Logging**: Comprehensive logging for monitoring and debugging

## Project Structure

```
art_critic_twitter/
├── main.py                 # Main entry point
├── bot.py                  # Core bot logic and orchestration
├── config.py               # Configuration management
├── state.py                # State persistence for processed tweets
├── twitter_client.py       # Twitter API interactions
├── venice_api.py           # Venice AI API interactions
├── image_processor.py      # Image downloading and processing
├── twitter_art_critic.py   # Legacy entry point
├── requirements.txt         # Python dependencies
├── env_example.txt         # Environment variables template
└── README.md              # This file
```

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/sabrinaaquino/art_critic_twitter.git
   cd art_critic_twitter
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**:
   ```bash
   cp env_example.txt .env
   ```
   
   Edit `.env` with your API keys:
   ```
   TWITTER_BEARER_TOKEN=your_twitter_bearer_token
   TWITTER_API_KEY=your_twitter_api_key
   TWITTER_API_SECRET=your_twitter_api_secret
   TWITTER_ACCESS_TOKEN=your_twitter_access_token
   TWITTER_ACCESS_TOKEN_SECRET=your_twitter_access_token_secret
   VENICE_API_KEY=your_venice_api_key
   ```

## Usage

### Running the Bot

**Using the new modular structure (recommended)**:
```bash
python main.py
```

**Using the legacy entry point**:
```bash
python twitter_art_critic.py
```

### How It Works

1. **Mention Monitoring**: The bot checks for new mentions every 60 seconds
2. **Image Detection**: When a mention contains an image, it downloads and processes it
3. **Art Critique**: The image is sent to Venice AI for analysis and critique generation
4. **Response**: The bot replies to the original tweet with the critique
5. **State Tracking**: Processed tweets are tracked to avoid duplicate responses

## Configuration

All configuration is centralized in `config.py`. Key settings include:

- `CHECK_INTERVAL`: Seconds between mention checks (default: 60)
- `MAX_MENTIONS_PER_CHECK`: Maximum mentions to process per cycle (default: 10)
- `SYSTEM_PROMPT`: The art critic personality prompt
- `NO_IMAGE_MESSAGE`: Message when no image is found
- `ERROR_MESSAGE`: Message when API errors occur

## Modules

### `main.py`
Entry point that initializes logging and starts the bot.

### `bot.py`
Core bot logic that orchestrates all components:
- Manages the main bot loop
- Coordinates between Twitter and Venice APIs
- Handles state persistence

### `config.py`
Centralized configuration management:
- Environment variable loading
- Configuration validation
- Default settings

### `state.py`
State persistence for tracking processed tweets:
- JSON-based storage
- Prevents duplicate processing
- Automatic save/load

### `twitter_client.py`
Twitter API interactions:
- Client initialization
- Mention retrieval
- Tweet replies

### `venice_api.py`
Venice AI API integration:
- Image analysis requests
- Critique generation
- Error handling

### `image_processor.py`
Image handling utilities:
- Image downloading
- Media attachment processing
- Error handling for image operations

## API Requirements

### Twitter API
- Bearer Token
- API Key
- API Secret
- Access Token
- Access Token Secret

### Venice AI API
- API Key for image analysis

## Error Handling

The bot includes comprehensive error handling:
- **API Rate Limits**: Automatic retry with exponential backoff
- **Network Issues**: Graceful degradation and retry
- **Invalid Images**: Skip processing and notify user
- **Missing Environment Variables**: Clear error messages

## Logging

The bot uses structured logging with configurable levels:
- **INFO**: Normal operation messages
- **ERROR**: Error conditions and exceptions
- **DEBUG**: Detailed debugging information (when enabled)

## State Management

The bot maintains state in `state.json` to track:
- Processed tweet IDs
- Avoid duplicate responses
- Persist across restarts

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 

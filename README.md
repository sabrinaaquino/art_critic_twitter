# Venice Art Critic Twitter Bot

A Twitter/X bot that critiques artwork using the Venice API. Similar to the Discord art critic bot, this bot responds to mentions with image attachments and provides honest, direct art critiques.

## Features

- Responds to Twitter mentions with image attachments
- Uses Venice API for intelligent art critique
- Provides honest and direct feedback on artwork
- Handles multiple image formats
- Rate limiting and error handling included

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Twitter API Setup

1. Go to [Twitter Developer Portal](https://developer.twitter.com/)
2. Create a new app and get your API credentials
3. You'll need:
   - Bearer Token
   - API Key
   - API Secret
   - Access Token
   - Access Token Secret

### 3. Venice API Setup

1. Get your Venice API key from [Venice AI](https://venice.ai/)
2. Add it to your environment variables

### 4. Environment Variables

Copy `env_example.txt` to `.env` and fill in your credentials:

```bash
cp env_example.txt .env
```

Then edit `.env` with your actual API keys.

### 5. Run the Bot

```bash
python twitter_art_critic.py
```

## Usage

1. Mention the bot in a tweet with an image attachment
2. The bot will analyze the image and provide an art critique
3. If no image is attached, the bot will ask for one

## Requirements

- Python 3.7+
- Twitter API v2 access
- Venice API key
- Internet connection for API calls

## Error Handling

The bot includes comprehensive error handling for:
- API rate limits
- Network issues
- Invalid image formats
- Missing API credentials 

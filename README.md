# Telegram News Monitor

## Setup Instructions

1. First, obtain your Telegram API credentials:
   - Visit https://my.telegram.org/apps
   - Create a new application
   - Note down your API_ID and API_HASH

2. Create a `.env` file in the project root with the following variables:
   ```
   API_ID=your_api_id
   API_HASH=your_api_hash
   MONITORED_GROUPS=group1,group2
   MISTRAL_API_KEY=your_mistral_api_key
   ADMIN_CHAT_ID=your_chat_id
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the monitor:
   ```bash
   python group_monitor.py
   ```

## First-time Authentication

When running the monitor for the first time, you'll need to authenticate with Telegram:

1. The script will prompt for your phone number
2. Enter your phone number with country code (e.g., +1234567890)
3. You'll receive a verification code via Telegram
4. Enter the code when prompted

After successful authentication, your session will be saved and you won't need to authenticate again.

## Monitoring Groups

Specify the groups to monitor in the MONITORED_GROUPS environment variable. You can use:
- Group usernames (e.g., @groupname)
- Group invite links (e.g., https://t.me/groupname)
- Multiple groups separated by commas

## Troubleshooting

- If you get a "phone number invalid" error, make sure to include the country code
- If authentication fails, delete the `*.session` file and try again
- For group access issues, ensure you're a member of the groups you want to monitor with GPT Analysis

This application monitors Telegram news channels, analyzes messages using GPT, and provides market-related insights and recommendations.

## Features

- Monitors specified Telegram news channels
- Analyzes news content using GPT-4
- Generates summaries and market action recommendations
- Stores analysis results in SQLite database
- Optional notifications to admin via Telegram

## Setup

1. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure environment variables:
   - Copy `.env.example` to `.env`
   - Add your Telegram Bot Token (get from @BotFather)
   - Add your OpenAI API Key
   - (Optional) Add your Telegram Chat ID for receiving analysis

3. Add the bot to your target news channels as an administrator

## Running the Application

```bash
python main.py
```

## Database

The application stores all analyses in `news_analysis.db` with the following information:
- Original message
- Summary
- Recommended market action
- Timestamp

## Note

Ensure your bot has the following permissions in the target channels:
- Read messages
- Read channel history
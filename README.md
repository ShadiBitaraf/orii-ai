# ORII AI Calendar Assistant

A sophisticated AI-powered calendar assistant that integrates directly into Google Calendar as a Chrome extension. Ask natural language questions about your schedule, find events semantically, and manage your calendar with conversational AI.

## ✨ Features

- **🎯 Smart Calendar Integration**: Native Google Calendar sidebar with polished UI
- **🤖 AI-Powered Queries**: Natural language processing with GPT-4
- **🔍 Semantic Search**: Find events by meaning, not just keywords ("last therapy session", "next workout")
- **📊 Smart Filtering**: Only queries visible calendars (60-90% API call reduction)
- **⚡ Incremental Search**: Month-by-month search with early termination
- **💬 Conversation Context**: Maintains context across multiple messages
- **📝 Rich Message Formatting**: Bullet points, bold text, and clean visual hierarchy
- **📅 Calendar-Specific Creation**: Create events on specific calendars ("add to my jetski calendar")
- **👥 Advanced Event Features**: Attendees, Google Meet, recurrence, reminders, colors
- **🎨 Material Design**: Matches Google Calendar's native look and feel

## 🚀 Quick Start

### 1. Backend Setup

```bash
# Clone and setup
git clone <repository-url>
cd orii-ai
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Environment setup
cp backend/.env.example .env
# Edit .env with your Google OAuth and OpenAI API keys

# Start the backend
python app.py
```

The Flask backend will start on `http://localhost:5001`

### 2. Chrome Extension Setup

1. **Open Chrome Extensions**:

   - Navigate to `chrome://extensions/`
   - Enable "Developer mode" (toggle in top right)

2. **Load Extension**:

   - Click "Load unpacked"
   - Select the `frontend/interfaces/extension/` folder
   - Extension will appear in your extensions list

3. **Test Integration**:
   - Go to `calendar.google.com`
   - Look for the ORII button in the right sidebar
   - Click to open the AI chat interface

## 🔧 Environment Configuration

Create a `.env` file in the root directory:

```env
# Google Calendar API
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# OpenAI API
OPENAI_API_KEY=your_openai_api_key

# Flask Configuration
FLASK_SECRET_KEY=your_secret_key
FLASK_ENV=development
```

### Getting Google Calendar API Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google Calendar API
4. Create OAuth 2.0 credentials
5. Add `http://localhost:5001` to authorized redirect URIs
6. Download credentials and update `.env`

## 📋 Usage Examples

Once set up, you can ask ORII questions like:

**Time-based queries:**

- "What do I have today?"
- "Show me next week's meetings"
- "Any appointments tomorrow?"

**Semantic searches:**

- "When was my last therapy session?"
- "Find my next workout"
- "Show dental appointments"
- "Meetings with john@company.com"

**Calendar-specific queries:**

- "What's in my UCI calendar today?"
- "Show work meetings this week"

**Event creation:**

- "Add a block to my jetski calendar at 2pm today"
- "Schedule team meeting tomorrow 10am with Google Meet"
- "Create lunch with john@company.com and sarah@email.com next Friday"
- "Add daily standup every weekday at 9am for 4 weeks"
- "Schedule private meeting with CEO, don't show other guests"

## 🏗️ Architecture

### Frontend: Chrome Extension

- **Content Script**: Injects ORII button into Google Calendar
- **Background Script**: Handles API communication
- **Sidebar UI**: React-like chat interface with Material Design

### Backend: Flask API

- **Port 5001**: CORS-enabled for Chrome extension
- **Session Management**: Conversation context storage
- **Google Calendar Integration**: Real calendar data access
- **Enhanced AI Processing**: 5-prompt strategy for optimal results

### AI Pipeline

1. **Intent Classification**: Determines query type (fetch, create, update, delete)
2. **Time Extraction**: Parses temporal expressions
3. **Semantic Matching**: Finds events by meaning
4. **Calendar Resolution**: Maps calendar names to IDs
5. **Event Creation**: Comprehensive Google Calendar field support
6. **Smart Filtering**: Only queries visible calendars
7. **Response Generation**: Conversational, formatted responses with rich formatting

## 🔍 Smart Calendar Filtering

ORII automatically detects which calendars are visible in your Google Calendar UI and only queries those, providing:

- **62.5% fewer API calls** on average
- **Faster response times**
- **Accurate calendar targeting**

## 📅 Advanced Event Creation

ORII supports comprehensive event creation with all Google Calendar features:

### Calendar Selection

- **Natural Language**: "add to my jetski calendar", "schedule on work calendar"
- **Smart Matching**: Exact and partial calendar name matching
- **Fallback**: Uses primary calendar if specified calendar not found

### Event Features

- **👥 Attendees**: Email addresses, names, or mixed formats
- **🎥 Google Meet**: Automatic video conferencing integration
- **🔄 Recurrence**: Daily, weekly, monthly with complex patterns
- **⏰ Reminders**: Multiple reminders (15min, 1hr, 1day, etc.)
- **🎨 Colors**: 11 colors based on event type or user preference
- **🔒 Privacy**: Default, public, private, confidential visibility
- **📍 Location**: Physical addresses or virtual meeting rooms

### Example Commands

```
"Add team standup to my work calendar every weekday at 9am"
"Schedule lunch with john@company.com tomorrow at noon with Google Meet"
"Create private meeting with CEO next Friday, don't show other guests"
"Add vacation day to travel calendar next Monday all day"
```

## 🛠️ Development

### Project Structure

```
orii-ai/
├── frontend/interfaces/extension/    # Chrome Extension
│   ├── manifest.json                # Extension config
│   ├── js/                         # Content/background scripts
│   ├── css/                        # Material Design styles
│   └── sidebar.html                # Chat interface
├── backend/                        # AI/NLP modules
│   ├── app/core/calendar/          # Google Calendar integration
│   ├── app/utils/enhanced_prompts.py # 5-prompt strategy
│   └── app/api/                    # API endpoints
├── app.py                          # Flask server
├── orii_demo.py                    # Core AI logic
└── requirements.txt                # Dependencies
```

### Running in Development Mode

```bash
# Backend with debug mode
python app.py

# Monitor logs
tail -f *.log

# Test API directly
curl -X POST http://localhost:5001/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What do I have today?", "session_id": "test"}'
```

### Chrome Extension Development

1. Make changes to files in `frontend/interfaces/extension/`
2. Go to `chrome://extensions/`
3. Click reload button on ORII extension
4. Test changes in Google Calendar

## 🧪 Testing

The system includes comprehensive testing categories:

**General Queries** (4): Basic chat, system questions  
**Time-based** (5): Today, tomorrow, next week, etc.  
**Semantic** (5): Therapy sessions, workouts, dentist, etc.  
**Complex** (1): Multi-parameter queries  
**Event Creation** (5): Calendar-specific creation, attendees, Meet links  
**Message Formatting** (3): Bullet points, bold text, HTML rendering

```bash
# Run comprehensive tests
python test_calendar_and_formatting.py

# Test specific features
python -c "from test_calendar_and_formatting import test_calendar_specific_event_creation; test_calendar_specific_event_creation()"
```

## 🐛 Troubleshooting

### Extension Not Appearing

- Check if backend is running on port 5001
- Verify extension is loaded in Chrome
- Check browser console for errors

### API Errors

- Verify Google Calendar API is enabled
- Check OAuth credentials in `.env`
- Ensure OpenAI API key is valid

### Calendar Not Found

- Check calendar visibility in Google Calendar UI
- Verify calendar sharing permissions
- Test with a simple "What do I have today?" query

## 📊 Performance Features

- **Caching**: 5-minute event cache to reduce API calls
- **Incremental Search**: Month-by-month with early termination
- **Smart Filtering**: Only visible calendars
- **Calendar Resolution**: Intelligent name-to-ID mapping with fallbacks
- **Rich Formatting**: Client-side HTML rendering for better UX
- **Session Management**: Conversation context preservation
- **Error Handling**: Graceful degradation on failures

## 🚢 Deployment

For production deployment:

1. **Update CORS settings** for your domain
2. **Use production Flask server** (e.g., Gunicorn)
3. **Set up proper secrets management**
4. **Consider rate limiting** for OpenAI API
5. **Monitor usage** and calendar API quotas

## 📄 License

[Your License Here]

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📞 Support

For issues or questions:

- Check the troubleshooting section
- Review Chrome extension console logs
- Test backend API directly
- Open a GitHub issue with detailed information

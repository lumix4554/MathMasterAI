# MathMaster AI

<p align="center">
  <img src="assets/mathmaster-logo.svg" alt="MathMaster AI logo" width="520">
</p>

<p align="center">
  <strong>Telegram-based mathematics learning assistant</strong><br>
  Learn concepts, solve problems, practise exam topics, and track progress.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Platform-Telegram-26A5E4?logo=telegram&logoColor=white" alt="Telegram">
  <img src="https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/Math-SymPy-3B5526" alt="SymPy">
  <img src="https://img.shields.io/badge/Status-Active%20development-orange" alt="Status"><br>
  <img src="https://github.com/lumix4554/MathMasterAI/actions/workflows/python-check.yml/badge.svg" alt="Python checks">
</p>

**MathMaster AI** is an educational Telegram bot designed to make mathematics more approachable through interactive explanations, mathematical tools, structured practice, and AI-assisted learning.

The project brings together symbolic mathematics, graph visualisation, exam-oriented learning content, OCR experiments, and learner progress tracking in one Python application.

## Project documentation

- [Architecture overview](docs/ARCHITECTURE.md)
- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Example environment configuration](.env.example)

## Highlights

- **Math workspace:** calculate and transform expressions, solve equations, differentiate, integrate, find limits, simplify and factor expressions.
- **Visual mathematics:** create 2D plots, compare multiple functions, and explore 3D surfaces.
- **Matrix tools:** perform matrix operations through the bot interface.
- **Learning library:** a generated collection of 200+ short lesson cards, organised by topic and learning track.
- **Exam preparation:** topic and task maps for school mathematics, OGE, and basic and advanced EGE tracks.
- **Interactive practice:** generated questions, answer checking, explanations, practice sessions, and random practice.
- **Progress tracking:** user profiles, XP, levels, streaks, skill statistics, learning history, and scheduled review data.
- **AI tutor:** configurable integrations for OpenAI-compatible services, including OpenAI, Groq, xAI, DeepSeek, and local endpoints; a public AI endpoint is also configurable.
- **Photo input (optional):** OCR support through EasyOCR or Tesseract, with image preprocessing via Pillow.
- **Diagnostics:** self-tests, AI connectivity checks, logging, and polling recovery.

> AI and OCR availability depends on the configured provider, network access, installed optional packages, and (for Tesseract) the separately installed Tesseract executable.

## Screens and bot sections

The Telegram menu includes sections for:

| Section | What it does |
|---|---|
| Calculator / Solve | Mathematical calculations and problem solving |
| Graphs | 2D, multiple-function, and 3D graphing |
| Matrices | Matrix calculations |
| Lessons | Browse and search learning cards |
| Learning | Explore exam tracks and topic-based skills |
| Practice | Complete generated exercises and review explanations |
| Statistics | View learning progress |
| Photo | Submit an image for OCR processing when configured |
| AI | Ask the configured AI assistant |
| Daily task / Tip | Get a short learning prompt or study tip |
| Settings | View profile, history, diagnostics, and preferences |

## Technology

| Technology | Role |
|---|---|
| Python | Application logic |
| pyTelegramBotAPI | Telegram Bot API integration |
| SymPy | Symbolic mathematics and expression parsing |
| NumPy | Numerical operations and graph data |
| Matplotlib | 2D and 3D visualisation |
| Pillow | Image preprocessing |
| EasyOCR / pytesseract | Optional text recognition from images |
| SQLite | Persistent user, lesson, history, and progress data |
| requests | HTTP communication with AI services |

## Project structure

The current application is intentionally maintained as a single-file Python project:

```text
MathMasterAI/
├── math_bot Math Master.py   # Telegram bot and application logic
├── assets/                   # Project branding assets
├── docs/                     # Architecture and technical documentation
├── .github/                  # CI workflow and issue templates
├── README.md                 # Project documentation
├── CONTRIBUTING.md           # Contribution guidelines
├── SECURITY.md               # Security policy
├── requirements.txt          # Core Python dependencies
├── requirements-ocr.txt      # Optional OCR dependencies
├── .gitignore                # Local files and secrets excluded from Git
└── .env                      # Local configuration (create this yourself; not committed)
```

SQLite databases and log files are created locally at runtime and should not be committed.

## Getting started

### Requirements

- Python 3.11 or newer
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Internet connection for Telegram and remote AI providers
- Optional API key(s) for the AI provider you want to use

### 1. Clone the repository

```bash
git clone https://github.com/lumix4554/MathMasterAI.git
cd MathMasterAI
```

### 2. Create and activate a virtual environment

**Windows PowerShell**

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

For optional OCR dependencies:

```bash
pip install -r requirements-ocr.txt
```

EasyOCR may download model files on first use. For the Tesseract route, install the Tesseract OCR application separately and make sure it is available on your system PATH.

### 4. Configure environment variables

Create a file named `.env` in the project root. Never commit this file.

```env
BOT_TOKEN=your_telegram_bot_token

# Optional AI provider settings
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o

GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant

XAI_API_KEY=
XAI_MODEL=grok-3-latest

DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat

# Optional local OpenAI-compatible endpoint
LOCAL_LLM_BASE_URL=
LOCAL_LLM_API_KEY=
LOCAL_LLM_MODEL=llama3.1

# Optional runtime settings
OFFLINE_MODE=false
PUBLIC_AI_ENABLED=true
DB_PATH=mathmaster.sqlite3
LOG_LEVEL=INFO
```

At minimum, set `BOT_TOKEN`. AI provider keys are optional; configure only the provider(s) you intend to use. The application also supports provider base-URL settings and a configurable public AI endpoint. Review the configuration section in the source before deploying.

### 5. Start the bot

```bash
python "math_bot Math Master.py"
```

The bot uses Telegram long polling. Keep the process running while you want the bot to respond.

## Data and privacy

- User profiles, learning progress, lesson skills, review scheduling, and interaction history are stored in SQLite.
- Runtime logs are written locally; dialog logging can include message text and user metadata.
- Do not publish database files, logs, bot tokens, or AI credentials.
- If you deploy the bot for other people, review the logging and data-retention behaviour and provide an appropriate privacy notice.

## Security

**Never put real credentials in source code.** Configure secrets through environment variables or a local `.env` file. The repository's `.gitignore` excludes common local secret and runtime files.

If a token or API key has ever been committed, treat it as compromised: revoke or rotate it with the relevant provider. Removing it from the latest version does not erase it from Git history.

## Current implementation notes

- The bot is currently a single-file application, rather than a multi-package architecture.
- SymPy, NumPy, Matplotlib, Pillow, EasyOCR, and pytesseract are loaded conditionally; related features may be unavailable when dependencies are missing.
- OCR quality depends on image quality and the selected recognition engine.
- AI responses depend on external provider availability, credentials, model configuration, and network access.

## Roadmap

- Split the single-file application into maintainable modules.
- Add automated tests for the mathematical engine and learning flows.
- Add screenshots and short demo recordings.
- Improve deployment documentation and configuration validation.
- Expand the lesson library and adaptive practice experience.

## Author

**Alexey Novikov**

Built as an educational software project combining Python development, mathematics, Telegram automation, and AI integrations.

---

<p align="center">
  <sub>MathMaster AI · Make mathematics easier to explore, practise, and understand.</sub>
</p>

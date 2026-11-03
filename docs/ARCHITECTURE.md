# Architecture

MathMaster AI is currently implemented as a **single-file Python application**. The descriptions below identify logical responsibilities inside that file; they are not separate Python packages or modules.

## High-level flow

```text
Telegram user
     |
     v
Telegram Bot API (pyTelegramBotAPI)
     |
     v
Handlers and conversation flows
     |
     +-------------------+--------------------+
     |                   |                    |
     v                   v                    v
Math engine         Learning engine       AI provider layer
(SymPy/NumPy)       lessons/practice      HTTP/OpenAI-compatible
     |                   |                    |
     +-------------------+--------------------+
                         |
                         v
                 SQLite persistence
                         |
             +-----------+-----------+
             |                       |
             v                       v
       Progress/history         Runtime logs
```

## Main logical areas

| Area | Responsibility | Main dependencies |
|---|---|---|
| Configuration | Reads environment variables and optional local `.env`; configures paths and runtime flags | Python standard library |
| Telegram interface | Receives updates, routes commands/callbacks, and sends messages/media | pyTelegramBotAPI |
| Mathematical tools | Parses and transforms expressions, solves equations, calculates derivatives, integrals and limits | SymPy |
| Numerical and visual tools | Numerical calculations and 2D/3D plots | NumPy, Matplotlib |
| Learning content | Presents lesson cards and topic/skill tracks, including school and exam-oriented material | Python data structures |
| Practice | Creates exercises, checks answers, explains results, and manages practice sessions | Python, SymPy where applicable |
| Progress | Tracks profiles, XP, levels, streaks, skills, history, and review data | SQLite |
| AI integrations | Sends prompts to configured remote or local AI endpoints | requests |
| Image input | Preprocesses images and optionally extracts text | Pillow, EasyOCR or pytesseract/Tesseract |
| Diagnostics and operations | Logging, self-tests, provider checks, polling recovery, and single-instance protection where supported | Python standard library |

## Persistence

SQLite stores application data locally. The configured database path is controlled by `DB_PATH`; by default the application uses a database file in the project directory. Treat the database as runtime data: do not commit it or publish it as a sample containing real user information.

## Optional capabilities

Some libraries are imported conditionally. The application can therefore start with a reduced feature set when optional mathematical, plotting, or OCR packages are missing. AI features also depend on network access, provider credentials, model availability, and endpoint configuration.

- Core dependencies are listed in [requirements.txt](../requirements.txt).
- Optional OCR packages are listed in [requirements-ocr.txt](../requirements-ocr.txt).
- Local configuration is documented in [.env.example](../.env.example).

## Operational considerations

1. Run one bot process for a bot token. The application includes a single-instance lock on platforms where the required locking primitive is available.
2. Keep credentials in environment variables or an untracked `.env` file.
3. Protect SQLite files and logs. Dialog logging can contain message text and Telegram user metadata.
4. Back up the database before upgrades that may change persistence behaviour.
5. Treat external AI responses as untrusted content and do not use them as a substitute for validating mathematical results.

## Current limitations

- The codebase is not yet split into independently testable modules.
- Automated unit and integration test coverage has not yet been established.
- OCR accuracy depends on image quality and the selected OCR engine.
- AI availability and output quality depend on external services and configuration.

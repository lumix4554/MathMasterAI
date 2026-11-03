# Security Policy

## Supported status

MathMaster AI is an actively developed educational project. Security fixes are handled on a best-effort basis.

## Reporting a vulnerability

Please do not publish exploit details, credentials, personal information, or sensitive logs in a public issue.

Use GitHub's **Private vulnerability reporting** feature for this repository if it is enabled. Otherwise, contact the repository owner privately through a trusted channel and include:

- A concise description of the issue.
- Steps to reproduce it, using test data.
- Potential impact.
- Any suggested mitigation.

Allow reasonable time for investigation and a fix before public disclosure.

## Credential handling

- Store Telegram and AI-provider credentials in environment variables or an untracked local `.env` file.
- Never commit tokens, API keys, passwords, private endpoints, or production database files.
- If a credential is exposed, revoke or rotate it immediately. Removing it from the latest commit does not remove it from Git history.
- Review dialog logging before deploying to real users. Logs may contain message text and Telegram user metadata.
- Use least-privilege credentials and separate development credentials from production credentials.

## Data handling

The bot uses local SQLite persistence and runtime logs. Anyone deploying it for other users is responsible for access controls, retention, backups, and an appropriate privacy notice.

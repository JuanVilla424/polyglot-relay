# 🌐 polyglot-relay

![Build Status](https://github.com/JuanVilla424/polyglot-relay/actions/workflows/ci.yml/badge.svg?branch=main)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)
![Status](https://img.shields.io/badge/Status-Stable-green.svg)
![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)

**polyglot-relay** is a self-hosted Discord auto-translation bot. It replaces rate-limited SaaS translators (like iTranslator's 10,000 chars/server and 2,000 chars/user free-tier caps, with the full language catalog paywalled behind Premium) with a fully self-hosted pipeline: no character limits, no paywalled languages, and no dependency on a paid third-party translation API. Language detection runs on [LibreTranslate](https://github.com/LibreTranslate/LibreTranslate); the actual translation runs on a self-hosted [NLLB-200](https://github.com/facebookresearch/flores/tree/main/flores200) (Meta) model via [CTranslate2](https://github.com/OpenNMT/CTranslate2) for meaningfully better quality than Argos Translate alone.

Each server member sets their own preferred language once — directly, inherited from a role, or set for them by an admin. From then on, every message gets a **reply**, in the same channel, with a color-coded translation embed for every language actually active there, plus the server's configured fallback language — no extra click, and it doesn't ping the original author. A right-click "Translate Message" command is also available for one-off, ephemeral translations.

## 📚 Table of Contents

- [Features](#-features)
- [Getting Started](#-getting-started)
  - [Prerequisites](#-prerequisites)
  - [Installation](#-installation)
  - [Environment Setup](#-environment-setup)
  - [Discord Application Setup](#-discord-application-setup)
  - [Running the Bot](#-running-the-bot)
  - [Pre-Commit Hooks](#-pre-commit-hooks)
  - [Extra Steps](#-extra-steps)
- [Usage](#-usage)
- [Contributing](#-contributing)
- [License](#-license)
- [Contact](#-contact)

## 🌟 Features

- **No character limits:** self-hosted LibreTranslate, no free-tier caps to hit or vote-to-reset.
- **Full language catalog:** nothing paywalled behind a premium tier.
- **In-channel reply delivery:** translations post as a native reply to the original message, one color-coded embed per active language, visible to everyone who can see that channel — no thread to open, no ping to the author.
- **Flexible language configuration:** members set their own language, admins can set it for a specific member, a role, or the whole server as a fallback — an explicit setting always overrides a role default.
- **On-demand fallback:** right-click any message → Apps → "Translate Message" for a one-off ephemeral translation (no privileged Discord intent needed for this path).
- **Fully self-hosted:** three Docker services (`libretranslate` for language detection, `nllb` for translation, `bot`), no external translation API or third-party bot dependency.
- **Automated Version Control:** automatic version bumping, tagging, and promotion across branches (dev → test → prod → main).
- **Automated Release Notes:** GitHub Releases with categorized changelogs generated from conventional commits.

## 🚀 Getting Started

### 📋 Prerequisites

**To just run the bot** (self-hosting, no code changes):

- **Git:** Install [Git](https://git-scm.com/) to clone the repository.
- **Docker + Docker Compose:** runs all three services (`libretranslate`, `nllb`, `bot`) — see [Running the Bot](#-running-the-bot).

**To develop or contribute** _(development only, on top of the above)_:

- **GitHub Account:** You need a GitHub account to use GitHub Actions.
- **Python 3.12+:** for running the test suite and pre-commit hooks locally — the bot itself always runs in Docker, not from this venv.
- **NVM:** (Optional) Node.js installation environment versions control
- **Node.js 22.x+**: (Optional) (Required to Push) Used as lint orchestration manager in pre-commit and pre-push

### 🔨 Installation

1. **Clone the Repository**

   ```bash
   git clone https://github.com/JuanVilla424/polyglot-relay.git
   ```

2. Navigate to the Project Directory
   ```bash
    cd polyglot-relay
   ```

### 🔧 Environment Setup

_Development only — running the bot doesn't need this, it always runs in Docker (see [Running the Bot](#-running-the-bot)). This venv is only for running tests or pre-commit hooks locally._

**Mandatory: Setting Up a Python Virtual Environment**

Setting up a Python virtual environment ensures that dependencies are managed effectively and do not interfere with other projects.

1. **Create a Virtual Environment**

   ```bash
   python -m venv venv
   ```

2. **Activate the Virtual Environment**

   On Unix or MacOS:

   ```bash
   source venv/bin/activate
   ```

   On Windows:

   ```bash
    .\venv\Scripts\activate
   ```

   - or

   ```bash
    powershell.exe -ExecutionPolicy Bypass -File .\venv\Scripts\Activate.ps1
   ```

3. **Upgrade pip**

   ```bash
   pip install --upgrade pip
   ```

4. **Install Dependencies**

   ```bash
   pip install -r requirements.txt
   pip install poetry
   poetry lock
   poetry install
   ```

   - Deactivate the Virtual Environment

   When you're done, deactivate the environment:

   ```bash
    deactivate
   ```

5. **Docker Extra Steps**: Install Scoop and then install hadolint using scoop, refer to [Extra Steps](#-extra-steps)

### 🤖 Discord Application Setup

`polyglot-relay` needs its own Discord bot — this is a manual, one-time setup in the Discord Developer Portal (the bot token is a secret and must never be committed):

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**.
2. Under **Bot**, click **Reset Token** and copy it into your local `.env` as `DISCORD_BOT_TOKEN` (copy `.env.template` to `.env` first — `.env` is gitignored).
3. Still under **Bot** → **Privileged Gateway Intents**, enable **Message Content Intent** and **Server Members Intent**. Both toggles work without Discord's app-review process as long as the bot stays under the ~100-server visibility threshold — which is the case for a personal/private-server bot. Members Intent is what lets role-based language auto-translation (`/setrolelanguage`) enumerate who has which role; it isn't needed for `/setlanguage` or the right-click translate alone.
4. Under **OAuth2 → URL Generator**, select scopes `bot` and `applications.commands`, and permissions `Send Messages`, `Read Message History`, `Use Application Commands`. Open the generated URL to invite the bot to your server.
5. _(Optional)_ To get language-command activity (successes and rejected attempts) reported to a channel: enable Discord's **Developer Mode** (User Settings → Advanced), right-click the target channel → **Copy Channel ID**, and set it as `LOG_CHANNEL_ID` in `.env`. The bot needs `Send Messages` permission in that specific channel too.

### 🐳 Running the Bot

```bash
cp .env.template .env      # fill in DISCORD_BOT_TOKEN
docker compose up -d
```

This starts three services, none exposed outside the internal Docker network: `libretranslate` (language detection only — 50 languages as of v1.9.6), `nllb` (translation, via a self-hosted NLLB-200 distilled-600M model converted from Meta's official weights the first time it's needed), and `bot`. `libretranslate` downloads its models on first run (several minutes, multiple GB); `nllb` converts its model lazily on the first real translation request instead of at startup, so the very first translation after a fresh deploy is noticeably slower than the rest — all three (including the bot's own `data/user_languages.json`/`role_languages.json`/`server_language.json`) live in named Docker volumes, which inherit the right ownership from each image automatically (no host-side `chmod` needed) and persist across restarts. All three services have healthchecks; the bot's works via a heartbeat file (`/tmp/healthy`, touched every 30s while the gateway connection is alive) since it isn't an HTTP service.

If you're upgrading from an older deploy that used a `./data` bind mount, migrate the existing JSON files into the named volume before recreating the container: `docker run --rm -v ./data:/src:ro -v polyglot-relay_polyglot-relay-data:/dst alpine sh -c "cp /src/*.json /dst/ && chown -R 1000:1000 /dst"`.

Language coverage for translation is limited to the languages mapped in `app/lang_codes.py` (curated common languages, not the full FLORES-200/200-language set) — `/setlanguage` with an unmapped code fails with a clear error instead of mistranslating.

### 🛸 Pre-Commit Hooks

_Development only, for contributors — not needed to run the bot._

**Install and check pre-commit hooks**: MD files changes countermeasures, python format, python lint, yaml format, yaml lint, version control hook, changelog auto-generation

```bash
pre-commit install
pre-commit install -t pre-commit
pre-commit install -t pre-push
pre-commit autoupdate
pre-commit run --all-files
```

### 📌 Extra Steps

_Development only — installs `hadolint`, used by the pre-commit Dockerfile-lint hook. Not needed to run the bot._

1. **Docker**:
   - Using MacOs or Linux:
     ```bash
     brew install hadolint
     ```
   - On Windows **as non-admin user**:
     ```bash
     Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
     Invoke-RestMethod -Uri https://get.scoop.sh | Invoke-Expression
     scoop install hadolint
     ```

## 🛠️ Usage

### Bot Commands

- **`/setlanguage <code>`**: set your own preferred language (e.g. `es`, `en`, `fr`). Required before you're included in any translation replies, unless a role already covers you (see below).
- **`/clearlanguage`**: remove your own preferred language.
- **`/setuserlanguage <member> <code>`** _(admin, Manage Server permission)_: set someone else's language for them — for people who won't run the command themselves.
- **`/clearuserlanguage <member>`** _(admin)_: remove another member's explicit language.
- **`/setrolelanguage <role> <code>`** _(admin, Manage Server permission)_: any member with that role gets included in translation replies in that language by default. An explicit `/setlanguage`/`/setuserlanguage` for that person always overrides their role.
- **`/clearrolelanguage <role>`** _(admin)_: remove a role's language mapping.
- **`/setserverlanguage <code>`** _(admin, Manage Server permission)_: set this server's fallback translation language — always included in every translation reply, on top of whatever members/roles have configured. Defaults to English until an admin sets one.
- **`/clearserverlanguage`** _(admin)_: reset the server's fallback language back to the default (English).
- **`/languages`**: list every language code the bot currently supports, with its name.
- **`/help`**: summary of every command above, in one place.
- **Right-click a message → Apps → Translate Message**: on-demand ephemeral translation of that one message, visible only to you, regardless of whether you've set a language.
- **Right-click a message → Apps → Retry Translation** _(admin)_: manually re-runs the automatic translation on that specific message — for when it didn't fire on its own (e.g. the bot was down when the message was sent). Reports back (ephemeral) whether it sent a translation, found nothing to translate, or failed.
- **Automatic translation replies**: for every message, the bot collects the distinct languages (explicit or via role) among members who can actually see that channel, skipping the author and any language that already matches the detected source, and always includes the server's fallback language (English by default, override with `/setserverlanguage`). If at least one applies, it replies to the message in the same channel — public, not a DM, not a thread, and it doesn't ping the original author (Discord's native reply reference links back to the source message on its own). Each language gets its own color-coded embed (title `code — Name`, a fixed color per code from `app/lang_codes.py`'s validated 8-color categorical palette, reused past the 8th language — identity is never color-alone, the code/name text is always there too) so languages are visually distinguishable at a glance. Batched across multiple reply messages if there are more than 10 active languages or the combined text is large (Discord's per-message embed count/size limits). If nobody in the channel has a language configured, no reply is sent. There's no per-channel throttling, but translation requests to the `nllb` service are capped at 2 concurrent in-flight calls to avoid saturating it during a burst.

### CI/CD Pipeline

**To customize the CI/CD pipeline for this repo, follow these steps**:

1. **Configure GitHub Actions**
   - Navigate to the .github/workflows/ directory.
   - Customize the ci.yml file according to your project's requirements.
   - Customize the python.yml file to format and lint python code.
   - Customize the release-controller file to add or remove **[app, tests, docker deployment]**

2. **Set Up Secrets**
   - Go to your GitHub repository settings.
   - Navigate to Secrets and add necessary secrets like CODECOV_KEY, etc.
   - Add `ACCESS_TOKEN` (Personal Access Token) for cross-repository submodule access and workflow triggers.

3. **Triggering the Pipeline**
   - Push to Branches: Pushing code to dev, test, prod, or main branches will trigger the pipeline.
   - Pull Requests: Opening or updating pull requests will run tests and checks.

4. **Version Bumping & Releases**
   - Add `[patch candidate]`, `[minor candidate]`, or `[major candidate]` to your commit message to trigger a version bump.
   - The pre-push hooks will automatically bump the version in `pyproject.toml` and amend the commit.
   - The Version Controller workflow creates tags and promotion PRs across the branch chain (dev → test → prod → main).
   - On main, a GitHub Release is automatically created with categorized release notes parsed from conventional commits.

5. **Monitoring Pipeline Status**
   - Check the Actions tab in your GitHub repository to monitor the status of your workflows.
   - Integrate notifications with Slack, Email, or other communication tools for real-time updates.

## 🤝 Contributing

**Contributions are welcome! To contribute to this repository, please follow these steps**:

1. **Fork the Repository**

2. **Create a Feature Branch**

   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Commit Your Changes**

   ```bash
   git commit -m "feat(<scope>): your feature commit message - lower case"
   ```

4. **Push to the Branch**

   ```bash
   git push origin feature/your-feature-name
   ```

5. **Open a Pull Request into** `dev` **branch**

Please ensure your contributions adhere to the Code of Conduct and Contribution Guidelines.

### 🛠️ Adding a New Workflow

1. **Create a New Workflow File**

   ```bash
   touch .github/workflows/new-workflow.yml
   ```

2. **Define the Workflow**

   Customize the workflow according to your needs, using existing workflows as references.

3. **Commit and Push**
   ```bash
   git add .github/workflows/new-workflow.yml
   git commit -m "chore(core): added new workflow - lower case"
   git push origin feature/your-feature-name
   ```

## 📫 Contact

For any inquiries or support, please open an issue or contact [r6ty5r296it6tl4eg5m.constant214@passinbox.com](mailto:r6ty5r296it6tl4eg5m.constant214@passinbox.com).

---

## 📜 License

2026 - This project is licensed under the [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.en.html). You are free to use, modify, and distribute this software under the terms of the GPL-3.0 license. For more details, please refer to the [LICENSE](LICENSE) file included in this repository.

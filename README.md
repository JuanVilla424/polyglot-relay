# 🌐 polyglot-relay

![Build Status](https://github.com/JuanVilla424/polyglot-relay/actions/workflows/ci.yml/badge.svg?branch=main)
![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)
![Status](https://img.shields.io/badge/Status-Stable-green.svg)
![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)

**polyglot-relay** is a self-hosted translation relay for **Discord and Slack**. It replaces rate-limited SaaS translators (like iTranslator's 10,000 chars/server and 2,000 chars/user free-tier caps, with the full language catalog paywalled behind Premium) with a fully self-hosted pipeline: no character limits, no paywalled languages, and no dependency on a paid third-party translation API. Language detection runs on [LibreTranslate](https://github.com/LibreTranslate/LibreTranslate); the actual translation runs on a self-hosted [NLLB-200](https://github.com/facebookresearch/flores/tree/main/flores200) (Meta) model via [CTranslate2](https://github.com/OpenNMT/CTranslate2) for meaningfully better quality than Argos Translate alone.

Both platform adapters share the same translation core (`core/` plus the `nllb` and `libretranslate` services) but run as fully separate Docker stacks: the Discord adapter is the full-featured bot described below, and the [Slack adapter](#-slack-adapter) is a deliberately quiet, on-demand-only workspace tool (message shortcut + flag reactions, everything delivered ephemerally).

Each server member sets their own preferred language once — directly, inherited from a role, or set for them by an admin. By default, every message gets one flag-emoji reaction per language actually active in that channel, plus the server's configured fallback language — nothing is translated upfront, so the channel stays quiet; clicking a flag posts a public, color-coded translation embed as a reply, visible to everyone. Admins can switch a server to always reply with every active language upfront, to thread delivery, or to private per-member DMs, instead with `/setbehavior`. A right-click "Translate Message" command is also available for one-off, ephemeral translations.

## 📚 Table of Contents

- [Features](#-features)
- [Getting Started](#-getting-started)
  - [Prerequisites](#-prerequisites)
  - [Installation](#-installation)
  - [Environment Setup](#-environment-setup)
  - [Discord Application Setup](#-discord-application-setup)
  - [Running the Bot](#-running-the-bot)
  - [Translation Glossary](#-translation-glossary)
  - [Slack Adapter](#-slack-adapter)
  - [Pre-Commit Hooks](#-pre-commit-hooks)
  - [Extra Steps](#-extra-steps)
- [Usage](#-usage)
- [Contributing](#-contributing)
- [License](#-license)
- [Contact](#-contact)

## 🌟 Features

- **No character limits:** self-hosted LibreTranslate, no free-tier caps to hit or vote-to-reset.
- **Full language catalog:** nothing paywalled behind a premium tier.
- **Flag-reaction delivery by default:** the bot reacts to every message with one flag per language active in that channel — no translation happens, and no noise, until someone clicks one. Clicking a flag translates on demand, publicly, as a native reply. Admins can opt a server into always-on reply delivery, thread delivery, or private per-member DMs instead, with `/setbehavior`.
- **Flexible language configuration:** members set their own language, admins can set it for a specific member, a role, or the whole server as a fallback — an explicit setting always overrides a role default.
- **On-demand fallback:** right-click any message → Apps → "Translate Message" for a one-off ephemeral translation (no privileged Discord intent needed for this path).
- **Modular:** built as a small platform of independent modules — Translation is on by default, and admins opt into others per server with `/polyglot-modules`. The Events module adds alliance event planning with RSVP flag reactions and automatic reminders (1h/30min/10min/at-start, mentioning only who confirmed), a free self-hosted alternative to paid bots like Raid-Helper. The Polls module posts native Discord polls with a simple `;`-separated options syntax and an admin "End Poll" early-close command. The Activity module gives admins an on-demand and weekly view of who's gone quiet, without ever leaving your own infrastructure.
- **Fully self-hosted:** three Docker services per stack (`libretranslate` for language detection, `nllb` for translation, plus the platform adapter), no external translation API or third-party bot dependency — your messages never leave your own infrastructure.
- **Slack adapter:** the same translation core in a Slack workspace, as a separate stack — on-demand and ephemeral only (a "Translate message" shortcut and flag-emoji reactions, visible only to whoever asked), connected via Socket Mode so it needs no public endpoint. See [Slack Adapter](#-slack-adapter).
- **Per-deployment glossary:** terms the model must never translate (product names, in-game vocabulary) live in a mounted JSON file per deployment, not in this repo — see [Translation Glossary](#-translation-glossary).
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
4. Under **OAuth2 → URL Generator**, select scopes `bot` and `applications.commands`, and permissions `Send Messages`, `Read Message History`, `Use Application Commands`, `Add Reactions` (needed for the default flag-reactions delivery — see Bot Commands below). Open the generated URL to invite the bot to your server. If you plan to switch a server to `/setbehavior thread`, also select `Create Public Threads` and `Send Messages in Threads` — not needed for reply or reactions mode, nor for `/setbehavior dm` (sending a DM to a shared-server member doesn't require any server permission). If you plan to enable the events module (`/polyglot-modules enable events`), also select `Manage Events` (so `/createvent` can also create a native Discord Scheduled Event, not just the bot's own embed -- without it, that part is silently skipped and logged, the rest of the event still works) and, if you want to attach images to events, `Attach Files`. Reopening the same invite URL with an updated permission selection re-grants them to an already-invited bot without duplicating it.
5. _(Optional)_ To get language-command activity (successes and rejected attempts) reported to a channel: enable Discord's **Developer Mode** (User Settings → Advanced), right-click the target channel → **Copy Channel ID**, and set it as `LOG_CHANNEL_ID` in `.env`. The bot needs `Send Messages` permission in that specific channel too.

### 🐳 Running the Bot

```bash
cp .env.template .env      # fill in DISCORD_BOT_TOKEN
docker compose up -d
```

This starts three services, none exposed outside the internal Docker network: `libretranslate` (language detection only — 50 languages as of v1.9.6), `nllb` (translation, via a self-hosted NLLB-200 distilled-600M model converted from Meta's official weights the first time it's needed), and `bot`. `libretranslate` downloads its models on first run (several minutes, multiple GB); `nllb` converts its model lazily on the first real translation request instead of at startup, so the very first translation after a fresh deploy is noticeably slower than the rest — all three (including the bot's own `data/user_languages.json`/`role_languages.json`/`server_language.json`) live in named Docker volumes, which inherit the right ownership from each image automatically (no host-side `chmod` needed) and persist across restarts. All three services have healthchecks; the bot's works via a heartbeat file (`/tmp/healthy`, touched every 30s while the gateway connection is alive) since it isn't an HTTP service.

If you're upgrading from an older deploy that used a `./data` bind mount, migrate the existing JSON files into the named volume before recreating the container: `docker run --rm -v ./data:/src:ro -v polyglot-relay_polyglot-relay-data:/dst alpine sh -c "cp /src/*.json /dst/ && chown -R 1000:1000 /dst"`.

After the first launch, redeploy with `./deploy.sh [service]` instead of a plain `docker compose build`/`up` (`service` defaults to `bot`; use `./deploy.sh nllb` or `./deploy.sh libretranslate` for the other two). It refuses to run if there are uncommitted changes. For `bot` specifically, it also bakes the current git commit and a short commit log into the image (`deploy_sha.txt`/`deploy_commit_log.txt`) — the bot reads those on startup to post what changed to `LOG_CHANNEL_ID` (set up above), keyed on the actual deployed commit rather than a version bump.

Language coverage for translation is limited to the languages mapped in `core/lang_codes.py` (curated common languages, not the full FLORES-200/200-language set) — `/setlanguage` with an unmapped code fails with a clear error instead of mistranslating.

### 📖 Translation Glossary

Some terms must survive translation verbatim — product names, in-game vocabulary, all-caps UI labels. The `nllb` service protects them via a **per-deployment glossary file**, mounted read-only into the container (`./config:/config`, read from `GLOSSARY_PATH`, default `/config/glossary.json`):

```bash
cp config/glossary.example.json config/glossary.json   # then edit for your deployment
```

- `config/glossary.json` is **gitignored** — each deployment's vocabulary stays out of this public repo. The committed `config/glossary.example.json` (the in-game glossary this project was born with) is a real, working example.
- Schema: `{"any_case": [...], "exact_case": [...]}`. `any_case` terms match case-insensitively with word boundaries and are restored with the author's exact casing; `exact_case` is for all-caps labels (`"SUMMON"`) whose lowercase forms are ordinary words that must stay translatable.
- No file (or an invalid one) degrades to an **empty glossary** with a logged warning — translation keeps working, nothing is protected.
- Changes to the file are picked up on the next `nllb` container start (`./deploy.sh nllb`, or `docker compose restart nllb` — the file is a mount, so a restart is enough for this one case).

### 💼 Slack Adapter

The Slack adapter brings the same self-hosted translation pipeline to a Slack workspace, as a **fully separate Docker stack** (own containers, own volumes, own `.env`) — deliberately minimal and quiet for a workspace context: nothing is ever posted publicly, translations are visible only to whoever asked for them.

**Create the Slack app** (one-time, manual — tokens are secrets and never committed):

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From a manifest**, and paste `slack_app/manifest.yml`. It declares the minimal bot scopes (`channels:history`, `groups:history`, `reactions:read`, `chat:write`, `commands`), the event subscriptions, the message shortcut, the `/polyglot-lang` command, and Socket Mode.
2. Under **Basic Information → App-Level Tokens**, generate a token with the `connections:write` scope — this is `SLACK_APP_TOKEN` (`xapp-...`), required for Socket Mode.
3. **Install the app to the workspace** (Install App). Copy the **Bot User OAuth Token** (`xoxb-...`) from **OAuth & Permissions** — this is `SLACK_BOT_TOKEN`.

**Run the stack:**

```bash
cp .env.slack.template .env    # fill in SLACK_BOT_TOKEN + SLACK_APP_TOKEN
cp config/glossary.example.json config/glossary.json   # or write your own glossary
docker compose -f docker-compose.slack.yml up -d --build
```

Socket Mode keeps every connection outbound (a websocket over 443) — no public endpoint, no inbound ports, so the stack runs anywhere Docker does.

**Usage:**

- The bot only sees the channels it's **invited to** — `/invite @polyglot-relay` in a channel is the whole opt-in.
- **`/polyglot-lang <code>`** sets your preferred language (`/polyglot-lang clear` removes it, `/polyglot-lang list` shows every supported code). Without one, translations fall back to the deployment's `DEFAULT_TARGET_LANGUAGE`.
- **Message shortcut** — hover a message → ⋮ → **Translate message**: translates it to your language, shown only to you (original included underneath for verification).
- **Flag-emoji reaction** (e.g. `:flag-co:`): translates that message to the flag's language, again only for you. This path resolves the message text from an in-memory cache of recent messages — Slack's `reaction_added` event doesn't carry the text, and `conversations.history` is rate-limited to ~1 request/minute for new non-Marketplace apps, so a message from before the bot's last restart (and out of the cache) may answer "too old to translate on demand". The shortcut has no such limit: its payload carries the message itself.
- Scope is **translation only**: the events/polls/verification/activity modules are Discord-native (scheduled events, native polls, roles) and don't exist on Slack.

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

`polyglot-relay` is built as a small platform of independent modules, not a single monolithic bot — **Translation** is on by default in every server; **Events** is off by default and needs an admin to opt in. See [Modules](#-modules) below.

#### Core

- **`/polyglot-modules <enable|disable> <module>`** _(admin, Manage Server permission)_: turn a module on or off for this server.

#### Translation module

- **`/setlanguage <code>`**: set your own preferred language (e.g. `es`, `en`, `fr`). Required before you're included in any translations, unless a role already covers you (see below).
- **`/clearlanguage`**: remove your own preferred language.
- **`/setuserlanguage <member> <code>`** _(admin, Manage Server permission)_: set someone else's language for them — for people who won't run the command themselves.
- **`/clearuserlanguage <member>`** _(admin)_: remove another member's explicit language.
- **`/setrolelanguage <role> <code>`** _(admin, Manage Server permission)_: any member with that role gets included in translations in that language by default. An explicit `/setlanguage`/`/setuserlanguage` for that person always overrides their role.
- **`/clearrolelanguage <role>`** _(admin)_: remove a role's language mapping.
- **`/setserverlanguage <code>`** _(admin, Manage Server permission)_: set this server's fallback translation language — always included in every translation, on top of whatever members/roles have configured. Defaults to English until an admin sets one.
- **`/clearserverlanguage`** _(admin)_: reset the server's fallback language back to the default (English).
- **`/setbehavior <mode>`** _(admin, Manage Server permission)_: choose how translations are delivered — **Flag reactions** (default; the bot adds one flag emoji per active language to the message, and translates on demand — publicly, as a reply — only when someone reacts with one of those flags), **Reply in the channel** (translates every active language upfront, no reaction needed), **Open a thread**, or **DM each person privately** (only members who configured a language get a DM; there's no server-wide fallback in this mode, since nobody asked for an unsolicited private message). Picked from a dropdown, not typed.
- **`/clearbehavior`** _(admin)_: reset translation delivery back to the default (flag reactions).
- **`/languages`**: list every language code the bot currently supports, with its name.
- **`/help`**: summary of every command above, in one place.
- **Right-click a message → Apps → Translate Message**: on-demand ephemeral translation of that one message, visible only to you, regardless of whether you've set a language.
- **Right-click a message → Apps → Retry Translation** _(admin)_: manually re-runs the automatic translation on that specific message — for when it didn't fire on its own (e.g. the bot was down when the message was sent). Reports back (ephemeral) whether it delivered a translation, found nothing to translate, or failed.
- **Automatic translation delivery**: works in regular text channels, in threads, and in forum channel posts (a forum post is a thread under the hood). For **reply** and **thread** mode, the bot collects the distinct languages (explicit or via role) among members who can actually see that channel, skipping the author and any language that already matches the detected source, and always includes the server's fallback language (English by default, override with `/setserverlanguage`) — delivered in the same channel, public, either as a **reply** to the message (no extra click, doesn't ping the author, Discord's native reply reference links back to the source) or as a **thread** on the message, per the server's `/setbehavior` setting. Discord doesn't support nesting a thread inside a thread, so a message that's already inside a thread (including forum posts) always delivers as a reply, regardless of `/setbehavior`. In **DM** mode, there's no server-wide fallback and nothing is public: each member who configured a language (directly or via role) gets a private DM with just their translation — someone with DMs from server members disabled is silently skipped, everyone else still gets theirs. In **flag reactions** mode (the default), nothing is translated upfront: the bot adds one flag-emoji reaction per active language (from `core/lang_codes.py`'s `ISO_TO_FLAG` mapping — a language with no distinct country flag, like Catalan, is skipped) to the original message, and only translates when someone clicks one of those reactions, posting the result as a public reply visible to everyone in the channel — the closest equivalent to how iTranslator's own Flag-Reaction Feature works, since Discord doesn't let a bot show different content to different viewers of the same message. The bot ignores its own reactions (adding the flags never triggers a translation), and reacting with an unmapped emoji, or on a server not currently in reactions mode, does nothing. Each language gets its own color-coded embed (title `code — Name`, a fixed color per code from `core/lang_codes.py`'s validated 8-color categorical palette, reused past the 8th language — identity is never color-alone, the code/name text is always there too) so languages are visually distinguishable at a glance. Batched across multiple messages if there are more than 10 active languages or the combined text is large (Discord's per-message embed count/size limits). If nobody active has a language configured, nothing is sent. There's no per-channel throttling, but translation requests to the `nllb` service are capped at 2 concurrent in-flight calls to avoid saturating it during a burst.

#### Events module

_Off by default — an admin enables it per server with `/polyglot-modules enable events`._

- **`/createvent <title> <date> <time> <utc_offset> [description] [image]`** _(admin, Manage Server permission)_: post an event embed with the time shown as a native Discord timestamp (auto-converted to each viewer's own timezone) and a countdown, add the RSVP flag reactions, and schedule its reminders. `date` is `YYYY-MM-DD`, `time` is 24h `HH:MM`, `utc_offset` is a plain number (e.g. `-5`, `0`, `+2`) for the timezone those two are given in. `description` (extra details/coordinates) and `image` (a screenshot or map) are optional.
- React **✅ Going / ❓ Maybe / ❌ Not going** on an event message to RSVP — the embed updates live with who's in each category. Removing your reaction clears your RSVP.
- **`/listevents`**: list this server's upcoming events, soonest first, each with a live "N going" count.
- **Right-click an event message → Apps → Cancel Event** _(admin)_: stop tracking the event (no more reminders) and post a cancellation notice.
- **Reminders**: sent automatically 1 hour, 30 minutes, and 10 minutes before the event, and once more right at the event's start — each one mentions only the members who RSVP'd ✅ Going, so nobody gets pinged for an event they didn't confirm. Creating an event with less than an hour's notice silently skips whichever early reminders would already be in the past, instead of firing them all at once.
- **`/announceevent <title> <date> <time> <utc_offset> [reminder_minutes_before] [duration_minutes]`** _(admin, Manage Server permission)_: for real-world game events that affect the whole alliance (e.g. Strongest Lord, Wheel of Destiny) rather than something the bot schedules — posts an `@everyone` announcement to `ANNOUNCEMENTS_CHANNEL_ID` immediately, plus a single reminder `reminder_minutes_before` minutes ahead (default 30). No RSVP, since nobody confirms attendance to an in-game event. The bot never guesses these dates — an admin who already knows the real date (from the game itself) enters it once.

#### Verification module

_Off by default — an admin enables it per server with `/polyglot-modules enable verification`._

- **React ✅ on a member's photo in the verify channel** _(Admin/Officer/Leader role, configured via `VERIFY_APPROVER_ROLE_IDS`)_: grants the configured Verified + Member roles to whoever posted it, and adds a ✅ confirmation reaction — automates what used to be done by hand, the visual check itself still stays with the approver.
- **Optional Guest role removal**: if `GUEST_ROLE_ID` is set, that role is removed at the same time Verified + Member are granted (e.g. a "Guest" role given before verification) — leave it unset and this step is simply skipped, nothing else changes.
- Needs the bot's own role positioned above the roles it assigns/removes, and the "Manage Roles" permission — see [Environment Setup](#-environment-setup).

#### Polls module

_Off by default — an admin enables it per server with `/polyglot-modules enable polls`._

- **`/createpoll <question> <options> [duration_hours]`** _(admin, Manage Server permission)_: post a native Discord poll (shows up in Discord's own poll UI, with real vote counts). `options` is a single string with 2-10 answers separated by `;` (e.g. `"Yes; No; Maybe"`) — each answer up to 55 characters, the question up to 300. `duration_hours` defaults to 24 and caps at 168 (Discord's own 1-week limit). Every poll is single-choice; there's no image support, since Discord doesn't allow a poll and an attachment on the same message.
- **Right-click a poll message → Apps → End Poll** _(admin)_: close the poll immediately instead of waiting for its duration to elapse.
- Polls need no bot-side storage or configuration — Discord itself is the source of truth for the question, answers, votes, and expiry.

#### Activity module

_Off by default — an admin enables it per server with `/polyglot-modules enable activity`._

- **`/activityreport [inactive_days]`** _(admin, Manage Server permission)_: list members who haven't sent a message or added a reaction in at least `inactive_days` (default 7), plus members with no recorded activity at all — kept as a separate section, since that can mean either "joined before this module was enabled" or "genuinely never active," not the same thing as a recent dropoff.
- **Weekly digest**: the same report posts automatically to the configured log channel (`LOG_CHANNEL_ID`) once a week, per server, once the module has been enabled for at least that long — no separate channel or configuration needed.
- **No retroactive backfill**: the bot only knows about activity from the moment the module is enabled onward — there's no way to reconstruct history from before that.
- Counts both messages and reactions as activity — this only ever _records_ a timestamp, it never affects how reactions are handled by other modules (RSVP, verification approval, translation flag-clicks all still work exactly as before).

### 🧩 Modules

Every module lives under `app/modules/<name>/` with its own commands, message/reaction handlers, and storage — `app/main.py` is just the shared bootstrap (the Discord client, the command tree, and a dispatcher that routes each incoming message/reaction to whichever modules are enabled for that guild). An admin toggles a module with `/polyglot-modules`; `translation` is on by default everywhere (so existing servers see no change), any future module defaults to off until explicitly enabled. A command belonging to a disabled module still shows up in Discord's picker (there's no cheap way to hide slash commands per-guild) but replies that the module needs to be enabled first, instead of silently doing nothing.

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

## [1.0.5] - 2026-08-16

### Bug Fixes

- **core**: bump dependencies to patch dependabot vulnerabilities and alerts (`patch candidate`)

## [1.0.4] - 2026-08-16

### Features

- **core**: make translation delivery mode configurable per guild
- **core**: reply inline instead of opening a thread for auto-translation
- **core**: make the server-wide fallback language an admin command
- **core**: color-code each language in the translation thread
- **core**: add server-language fallback and admin retry-translation command
- **core**: translate in a public thread per channel instead of private dms
- **core**: show language names in /languages and add /help command
- **core**: close audit gaps - ci tests, healthchecks, named volume, concurrency limit, clear commands, languages command
- **core**: report language changes to a configurable log channel
- **core**: add admin and role-based language assignment
- **core**: add polyglot-relay discord auto-translation bot

### Bug Fixes

- **core**: split long combined translations into multiple thread messages
- **core**: add catalan mapping and isolate tests from the real .env
- **core**: switch translation engine to self-hosted nllb-200 for quality
- **core**: defer context menu translation to avoid discord interaction timeout
- **core**: document data volume permission fix for non-root bot user

### Documentation

- **core**: drop unrelated badges and hotlinked icon from readme header
- **core**: reflect thread-based translation and mark dev-only setup steps in readme

### Chores

- **core**: bump version (`patch candidate`)
- **core**: remove orphaned cazira submodule reference

### Other Changes

- Initial commit

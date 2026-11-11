## Purpose

Lets the set of supported source and target languages, and the OCR/translation providers used for each, be changed through configuration instead of an app release.

## ADDED Requirements

### Requirement: Configurable language list
The backend SHALL expose the list of supported source and target languages from a configuration source that can be updated without changing or releasing the Android app.

#### Scenario: Adding a new source language
- **WHEN** an operator adds a new source language to the backend configuration
- **THEN** the app's language picker offers that language without requiring an app update

### Requirement: Per-language provider mapping
The backend SHALL select its OCR and translation provider for a given language pair from configuration rather than from a value fixed in code.

#### Scenario: Provider changed for a language
- **WHEN** an operator updates the configured provider for a given source language
- **THEN** subsequent translation requests for that language use the newly configured provider

## Purpose

Provides a single backend entry point that turns a cropped camera image into recognized and translated text, so the Android app never holds or exposes the Sarvam API key.

## ADDED Requirements

### Requirement: Frame translation endpoint
The backend SHALL accept a cropped image along with a source and target language, and return the recognized source text, its translation, and a region hint.

#### Scenario: Successful translation request
- **WHEN** the app sends a cropped image with a valid source and target language
- **THEN** the backend returns the recognized text, its translation, and a region hint for that image

### Requirement: Cached repeat translations
The backend SHALL return a cached translation for source text it has already translated instead of issuing a new translation call.

#### Scenario: Same headline seen again
- **WHEN** the backend recognizes source text that matches a still-valid cache entry
- **THEN** the backend returns the cached translation without calling the translation provider again

### Requirement: Shared OCR rate budget
The backend SHALL limit outgoing OCR requests across all active users to stay within the OCR provider's rate limit.

#### Scenario: Rate budget exhausted
- **WHEN** the number of OCR requests in the current period has reached the provider's limit
- **THEN** the backend queues or defers additional OCR requests until budget is available, rather than exceeding the provider's limit

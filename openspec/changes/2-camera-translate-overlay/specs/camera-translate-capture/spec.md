## Purpose

Lets a person point their phone's camera at text they cannot read and see a translated overlay that tracks the text's position and refreshes automatically as the scene changes.

## ADDED Requirements

### Requirement: Live camera view with translated overlay
The Android app SHALL show a live camera preview with the translated text of any detected source-language text overlaid at that text's on-screen position.

#### Scenario: Text detected and translated
- **WHEN** a person points the camera at text in the configured source language
- **THEN** the app shows the translated text overlaid at the position of the source text

#### Scenario: Overlay stays while refresh is pending
- **WHEN** a new recognition/translation cycle has not yet completed since the last one
- **THEN** the app continues showing the last translated overlay instead of showing a blank or error state

### Requirement: Automatic refresh on scene change
The app SHALL automatically start a new recognition cycle on a periodic basis without requiring the person to tap a button.

#### Scenario: Headline changes
- **WHEN** the on-screen source text changes between refresh cycles
- **THEN** the overlay updates to the new translation within the next completed refresh cycle

### Requirement: Graceful handling of recognition failure
The app SHALL keep the last successfully translated overlay visible when a recognition or translation request fails or times out.

#### Scenario: Backend call times out
- **WHEN** the backend proxy returns an error or does not respond within the expected time
- **THEN** the app keeps displaying the previous successful overlay rather than an error message

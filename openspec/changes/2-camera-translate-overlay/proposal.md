# Camera translate overlay

## Why

People who don't read a given script have no way to get a live, updating translation of text in their camera's view; Sarvam already offers both the OCR and translation needed to build this. The motivating case: pointing a phone at Malayalam TV news headlines and seeing them in a chosen language within about 10 seconds, with the overlay refreshing on its own as the headline changes.

## What Changes

- Add a new Android app with a live camera view, on-device text-region detection, and an overlay renderer that anchors translated text to the tracked region on screen.
- Add a new backend proxy service that holds the Sarvam API key, performs OCR (submit/poll/download) and translation calls on the app's behalf, caches repeat translations, and enforces a shared OCR rate budget.
- Add a source/target language configuration that lives in the backend, not the app, so adding a language is a config change.

## Capabilities

### New Capabilities

- `camera-translate-capture`: live camera view with on-device text-region detection and an overlay anchored to tracked regions.
- `translate-proxy-service`: backend endpoint that turns a cropped frame into recognized and translated text, with caching and rate budgeting.
- `language-configuration`: source/target language list and provider mapping that can be updated without an app release.

### Modified Capabilities

- None. This is a greenfield repository: `openspec/specs/` is empty and there is no code, so every capability is new.

## Impact

- **Repositories:** the `mirror` repo (this one) holds both the Android app and the backend proxy service. No other repository is affected.
- **APIs:** new backend endpoint accepting a cropped image and returning recognized plus translated text and a region hint; this endpoint in turn calls Sarvam's OCR and translate APIs.
- **Data and privacy:** camera frames are sent to the backend and on to Sarvam for recognition, then discarded — the backend keeps no images. The only stored data is a short-lived cache keyed by a hash of the recognized source text, holding its translation. No user accounts, no personal data, no persistent history, no credentials in the app: the Sarvam API key lives only in the backend.
- **Provider facts** (verified against docs.sarvam.ai on 2026-11-09): Sarvam Document AI Parse accepts PNG/JPEG input, supports Malayalam (`ml-IN`) among 23 languages, and works asynchronously (submit, poll, download). Rate limits are per-account and plan-dependent: Parse allows 200 requests/minute and Translate 60 requests/minute on pay-as-you-go. The "10 requests/minute" figure in the original request does not match the current docs.
- **Open risk (does not change scope):** Sarvam's OCR is tuned for scanned documents. Recognition quality on cropped, angled, glare-prone photos of screens needs a spike with real sample photos before the refresh cadence is fixed. The graceful-degradation requirement covers failed cycles either way.

## Non-goals

- No iOS app in this change.
- No offline or on-device translation.
- No true frame-perfect (sub-1-second) refresh; refresh is periodic, bounded by Sarvam's OCR rate limit.
- No scripts beyond Sarvam's supported languages.
- No translating pre-recorded video files, only the live camera feed.

## Interpretations taken

1. "As the text changes it should have kept updating it" is read as an automatic periodic refresh (on the order of several seconds), not literal real-time video OCR, because no streaming OCR API exists to support frame-perfect updates.
2. Malayalam is treated as the first source language to support, with other Sarvam-supported languages addable later through configuration rather than a code change.
3. The app is built as its own standalone camera screen, not a filter or plugin on the phone's existing camera app, because no such integration point exists on Android.
4. "Always-online" is read as requiring a backend proxy service (rather than the app calling Sarvam directly), so the API key is never exposed inside the installed app.
5. The target language is treated as a single user-chosen language per session for this change, pending the open question on whether a switcher is needed.
6. The backend holds one shared Sarvam key with one shared per-account rate budget across all users; per-user Sarvam keys are not supported in this change.
7. The OCR and translate budget values are plan-dependent (200 OCR parses/minute and 60 translations/minute on pay-as-you-go today, per Sarvam's published limits), so they live in backend configuration rather than in code.

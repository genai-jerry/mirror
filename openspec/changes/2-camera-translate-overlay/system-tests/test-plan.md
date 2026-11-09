# System test plan — camera translate overlay

Epic: genai-jerry/mirror#2. Black-box cases a person runs against the
assembled epic, derived from `proposal.md`, `specs/` and `tasks.md` only.
Task numbers below are the tasks in `tasks.md`; data sets are defined in
`test-data.md` with their records under `system-tests/data/`.

## Scope

These cases prove, end to end on a running system, what the automated suite
cannot: a person pointing a real phone camera at real Malayalam text and
seeing the translated overlay appear, track, refresh, and survive failures;
and an operator changing backend configuration and seeing the change reach
the app with no release.

Every WHEN/THEN scenario in `specs/` is covered by at least one case — see
the traceability table at the end. Two aspects are deliberately left to the
automated suite:

- **Multi-user concurrency on the shared recognition budget.** ST-6 proves
  the budget defers calls past the limit using one device and a low budget;
  proving the limiter is shared and race-free across many simultaneous users
  is a load/concurrency test the automated suite owns.
- **Cache expiry timing.** ST-5 proves a repeat translation is answered from
  the cache; that an entry expires after exactly its configured lifetime is
  a clock-controlled unit test, not something a tester can observe reliably.

OCR quality on angled, glare-prone photos of screens is an open risk in
`proposal.md`, not a requirement; ST-1's display setup (below) is the
controlled version, and quality beyond it is the spike's job, not a verdict
here.

## Environment

Cases run as the epic assembles on the epic branch `factory/epic-2`. The
repo profile defines no preview environment yet, so the tester needs:

- The **backend** built from `factory/epic-2`, running where the tester can
  reach it, with a Sarvam API key configured in that environment (the key
  lives only in the backend — it is never in test data or the app). The
  backend scaffold task defines how to run it.
- The **Android app** built from `factory/epic-2`, installed on a physical
  Android phone with a working camera, pointed at that backend.
- A **second screen** (monitor or laptop) to display the DS-1 Malayalam
  headlines full-screen at a large font size, in good light, camera roughly
  square-on — the controlled version of the TV-headline case.
- **Backend log access** for the cases whose expected result reads provider
  calls from the log (ST-5, ST-6, ST-8, ST-9).
- The DS-2 and DS-3 configuration sets loaded with the `load` command in
  `test-data.md` where a case's preconditions say so.

## Test cases

### ST-1: Malayalam text is translated and overlaid at its position

- Covers: camera-translate-capture/Live camera view with translated overlay/Text detected and translated; translate-proxy-service/Frame translation endpoint/Successful translation request
- Depends on: Task 6, Task 8, Task 9
- Data: DS-1
- Execution: manual
- Preconditions: baseline configuration (Malayalam source, English target); backend reachable from the app.
- Steps:
  1. Display DS-1 headline H1 full-screen on the second screen.
  2. Open the app and point the camera at the headline, holding roughly steady.
  3. Wait up to 10 seconds without tapping anything.
- Expected: an English translation whose meaning matches H1's reference
  translation appears within about 10 seconds, drawn over the position of
  the Malayalam text in the camera view — not in a detached panel, and with
  no tap at any point. Wording may differ from the reference; meaning may not.

### ST-2: The overlay updates on its own when the headline changes

- Covers: camera-translate-capture/Automatic refresh on scene change/Headline changes
- Depends on: Task 6, Task 8, Task 9
- Data: DS-1
- Execution: manual
- Preconditions: ST-1's end state — the H1 overlay is showing.
- Steps:
  1. Without touching the phone, change the displayed headline from H1 to H2.
  2. Keep the camera pointed at the screen and wait for the next refresh cycle to complete.
- Expected: the overlay changes to H2's translation (meaning matching H2's
  reference) within the next completed refresh cycle, with no tap and no
  app interaction of any kind.

### ST-3: The last overlay stays while a refresh is pending

- Covers: camera-translate-capture/Live camera view with translated overlay/Overlay stays while refresh is pending
- Depends on: Task 6, Task 8, Task 9
- Data: DS-1
- Execution: manual
- Preconditions: the H1 overlay is showing.
- Steps:
  1. Keep the camera steady on H1 and watch the overlay continuously across at least three refresh cycles.
- Expected: the H1 translation stays visible the whole time. Between cycles
  the overlay never goes blank, never flickers to empty, and no error or
  loading state replaces it.

### ST-4: A backend outage keeps the last good overlay

- Covers: camera-translate-capture/Graceful handling of recognition failure/Backend call times out
- Depends on: Task 6, Task 8, Task 9
- Data: DS-1
- Execution: manual
- Preconditions: the H1 overlay is showing; the tester can stop the backend (or block the app's network path to it) and restore it.
- Steps:
  1. Stop the backend.
  2. Keep the camera pointed at H1 for at least two refresh cycles.
  3. Change the displayed headline to H2, wait two more cycles.
  4. Restore the backend and keep pointing at H2.
- Expected: while the backend is down, the H1 overlay stays on screen — no
  error message, no blank, through steps 2 and 3 (even though the on-screen
  text is now H2). After the backend is restored, the overlay catches up to
  H2's translation within one or two completed cycles.

### ST-5: The same headline is answered from the cache

- Covers: translate-proxy-service/Cached repeat translations/Same headline seen again
- Depends on: Task 4, Task 6, Task 8, Task 9
- Data: DS-1
- Execution: manual, automatable
- Preconditions: backend log access; note the clock time (UTC) when you start.
- Steps:
  1. Point the camera at H1 and hold steady until at least three refresh cycles have completed.
  2. Read the backend log for that window.
- Expected: the overlay shows H1's translation throughout. The log shows a
  recognition call per cycle, but only **one** translation provider call for
  H1's text in the whole window — every later cycle is answered from the
  cache with no new translation call.

### ST-6: A burst past the recognition budget is deferred, never over the limit

- Covers: translate-proxy-service/Shared OCR rate budget/Rate budget exhausted
- Depends on: Task 5, Task 6, Task 8, Task 9, Task 11
- Data: DS-1, DS-3
- Execution: manual
- Preconditions: DS-3 (recognition budget of 2 per minute) loaded with the `load` command; backend log access; note the start time (UTC).
- Steps:
  1. Point the camera at H1 and keep the app refreshing for two full minutes — the automatic refresh cadence will ask for more than 2 recognitions per minute on its own.
  2. Read the backend log for those two minutes.
- Expected: the backend sends at most 2 recognition calls to the provider in
  any one minute. Requests past the budget are deferred or queued — the log
  says so — and none is answered with a provider rate-limit error. On the
  phone, the last good overlay stays visible while deferred cycles wait;
  no error appears.

### ST-7: A language added in backend configuration appears in the picker

- Covers: language-configuration/Configurable language list/Adding a new source language
- Depends on: Task 2, Task 10, Task 11
- Data: DS-2
- Execution: manual
- Preconditions: baseline configuration loaded; the app installed and already opened at least once.
- Steps:
  1. Open the app's language picker and confirm Tamil is not offered as a source language.
  2. Apply DS-2's add-Tamil set with the `load` command. Do not update, reinstall or clear the app.
  3. Close and reopen the picker (restarting the app is allowed; reinstalling is not).
- Expected: Tamil now appears as a source language in the picker, on the
  same installed app build, with no app update.

### ST-8: A provider change in configuration takes effect on the next request

- Covers: language-configuration/Per-language provider mapping/Provider changed for a language
- Depends on: Task 2, Task 4, Task 6, Task 8, Task 9, Task 11
- Data: DS-1, DS-2
- Execution: manual
- Preconditions: baseline configuration loaded; backend log access.
- Steps:
  1. Point the camera at H1 until the overlay shows, and confirm in the log which translation provider answered.
  2. Apply DS-2's provider-change set with the `load` command (it maps Malayalam translation to the alternate configured provider entry).
  3. Point the camera at H3 — a headline not yet translated, so the cache cannot answer it — until its overlay shows.
  4. Read the log for the H3 request.
- Expected: the H3 translation request names the newly configured provider
  entry in the log — the change took effect on the next request, with no
  backend code change and no app change.

### ST-9: A request in an unconfigured language is rejected clearly

- Covers: translate-proxy-service/Frame translation endpoint/Successful translation request (the rejected-input boundary: "valid source and target language")
- Depends on: Task 6
- Data: DS-4
- Execution: manual, automatable
- Preconditions: baseline configuration (Malayalam and English only); backend log access; a machine that can send an HTTP request to the frame translation endpoint.
- Steps:
  1. Decode DS-4's sample image to a PNG file as its `how_to_use` says.
  2. Send it to the frame translation endpoint with source language `fr-FR` and target `en-IN` — a pair the configuration does not offer.
  3. Read the response and the backend log.
- Expected: the backend rejects the request with a clear error that names
  the unsupported language — not a timeout, not a blank 500. The log shows
  **no** recognition and **no** translation provider call for it: the
  request is refused before any provider is involved.

### ST-10: No text in view shows no overlay and no error

- Covers: camera-translate-capture/Live camera view with translated overlay/Text detected and translated (the empty boundary)
- Depends on: Task 8, Task 9
- Data: DS-1
- Execution: manual
- Preconditions: app open on the camera screen.
- Steps:
  1. Point the camera at a blank wall for at least three refresh cycles.
  2. Then point it at DS-1 headline H1 and wait up to 10 seconds.
- Expected: while the wall is in view, the camera preview stays live with no
  overlay, no error and no crash. Once H1 is in view, its translation
  appears within about 10 seconds as in ST-1.

## Traceability

| Capability | Requirement | Scenario | Covered by |
|---|---|---|---|
| camera-translate-capture | Live camera view with translated overlay | Text detected and translated | ST-1, ST-10 |
| camera-translate-capture | Live camera view with translated overlay | Overlay stays while refresh is pending | ST-3 |
| camera-translate-capture | Automatic refresh on scene change | Headline changes | ST-2 |
| camera-translate-capture | Graceful handling of recognition failure | Backend call times out | ST-4 |
| translate-proxy-service | Frame translation endpoint | Successful translation request | ST-1, ST-9 |
| translate-proxy-service | Cached repeat translations | Same headline seen again | ST-5 |
| translate-proxy-service | Shared OCR rate budget | Rate budget exhausted | ST-6 |
| language-configuration | Configurable language list | Adding a new source language | ST-7 |
| language-configuration | Per-language provider mapping | Provider changed for a language | ST-8 |

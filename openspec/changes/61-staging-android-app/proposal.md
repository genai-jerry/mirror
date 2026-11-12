# Installable staging Android app

## Why

The Mirror Android app can only be run by a developer who builds it on their own machine. Nobody else can install it on a phone and try it against the staging backend. The owner wants every merge to `staging` to assemble the app and publish an installable build for testers.

## What Changes

- Add a GitHub Actions workflow that, on a push to `staging` that changes the app, builds an installable Android app (APK) and publishes it as a GitHub pre-release on this repository, with the APK attached.
- Add a staging build of the app that talks to the staging backend. The backend address and app token come from GitHub secrets, not from the repository.
- Allow the staging build to use plain HTTP to the staging backend's address only. Every other server still needs HTTPS, as today.
- Sign every staging build with one fixed test key held in GitHub secrets, and give each build a higher version number than the last, so a new build installs over the previous one.
- Add a short guide: which secrets to set, how to make the test key, and how a tester installs the app from the pre-release.

## Capabilities

### New Capabilities

- `staging-app-distribution`: building, signing and publishing an installable staging build of the Android app on every app change that reaches `staging`.

### Modified Capabilities

- None. `openspec/specs/` is empty on `main`. The app's own requirements live in the mirror v1 epic and are not changed here, except for the one allowed plain-HTTP address of the new staging build.

## Impact

- **Repositories:** the `mirror` repo only. New: a workflow under `.github/workflows/`, a staging build in the app's build file, and a guide under `docs/`.
- **Depends on the mirror v1 epic.** The app exists today only on the mirror v1 epic's branch. That epic is being released to staging now. This change is written against that app. Its first real build happens once the app is on `staging`.
- **Depends on the backend deployment epic.** The staging backend comes from that epic, which is already on `staging`. Its `staging` GitHub Environment holds the backend's settings.
- **Verification limit.** The factory's runners have no Android SDK. No factory run can build the APK or run the workflow. A person must run the first build and install it on a phone. The workflow can be started by hand for that purpose.
- **Production gate.** Nothing here runs on `main`. Gate G3 is unchanged.

## Data and privacy

- The staging backend address and app token are secrets in the repository settings. They never appear in a file, a log or the pre-release notes.
- An installed APK carries the address and token inside it. Anyone with the APK can read them. This is acceptable for a test build on a private repository, and it matches how the app already treats its token ("a deterrent, not a secret").
- The signing key and its passwords are secrets. They never appear in a file or a log.
- No user data is collected or published by this change.

## Non-goals

- No Google Play release, Play Console track or Firebase App Distribution.
- No production app build. A merge to `main` publishes nothing.
- No HTTPS or domain name for the staging backend.
- No change to what the app does on screen.
- No automatic cleanup of old pre-releases. A person deletes them when they want.
- No build on pull requests or on the epic branches.

## Interpretations taken

1. Testers get the app from a GitHub pre-release on this repository, with the APK attached; testers sign in to GitHub on the phone because the repository is private (the owner's answer).
2. The staging build talks to the staging backend, with its address kept as a GitHub secret, and allows plain HTTP to that one address only (the default offered; no answer given).
3. The staging build sends the staging backend's app token, read from the same `staging` secrets the backend deployment uses, so a staging backend with its token switch on still accepts the app.
4. Every build is signed with one fixed test key kept in GitHub secrets, so a new build installs over the old one without uninstalling (the default offered; no answer given).
5. Each build's version number is higher than the one before it, so Android accepts it as an update.
6. Only a push to `staging` publishes an app; a merge to `main` publishes nothing (the default offered; no answer given).
7. A push to `staging` builds the app only when it changes the app or the build workflow; a push of documents or backend code alone builds nothing.
8. This work builds on the mirror v1 epic's app without waiting for it: the epic branch is cut from `main` as the factory policy requires, and the first real build waits until the app is on `staging` (the default offered; no answer given).
9. "Developer or test mode" is read as a test build that is clearly named as staging and can be installed from outside Google Play, not as Android's developer options on the phone.
10. A missing secret stops the build before anything is published, and the failure names the missing secret.

## Purpose

Assembles the Android app on every app change that reaches `staging` and publishes it as an installable, signed test build, so testers can install the app on a phone and use it against the staging backend.

## ADDED Requirements

### Requirement: Build on app changes that reach staging
The build SHALL run when a push to `staging` changes the app or the build workflow, SHALL be startable by hand on `staging`, and SHALL NOT run for any other branch, for a pull request, or for a push that changes neither.

#### Scenario: App change pushed to staging
- **WHEN** a commit that changes a file under `app/` is pushed to `staging`
- **THEN** the workflow builds the staging app and publishes it

#### Scenario: Push that does not touch the app
- **WHEN** a push to `staging` changes only documents, the backend or the deployment files
- **THEN** no app build runs and no pre-release is created

#### Scenario: Other branches and pull requests
- **WHEN** a commit is pushed to `main` or any other branch, or a pull request is opened or updated
- **THEN** no app build runs and no pre-release is created

#### Scenario: Manual run
- **WHEN** a person starts the workflow by hand on `staging`
- **THEN** the workflow builds and publishes the app from `staging`'s current commit

#### Scenario: App not on the branch yet
- **WHEN** the workflow runs on a `staging` commit that does not contain the app
- **THEN** the run fails with a message saying the app must reach `staging` first, and nothing is published

### Requirement: Published as a GitHub pre-release
Each successful build SHALL create a new GitHub pre-release on this repository with the signed APK attached, marked as a pre-release and never as the latest release, and naming the commit and the version it was built from.

#### Scenario: Pre-release created
- **WHEN** a staging build succeeds
- **THEN** a new pre-release exists with one APK attached, and its notes name the commit and the app version

#### Scenario: Not marked as a production release
- **WHEN** a staging pre-release is created
- **THEN** GitHub shows it as a pre-release, and it is not marked as the repository's latest release

#### Scenario: Failed build publishes nothing
- **WHEN** the app does not build or its unit tests fail
- **THEN** the run fails and no pre-release is created

### Requirement: Staging build talks to the staging backend
The staging build SHALL send every request to the staging backend address and SHALL send the staging app token, both read from GitHub secrets at build time, and no backend address or token SHALL appear in the repository.

#### Scenario: App reaches the staging backend
- **WHEN** a tester installs the staging build and points the camera at text
- **THEN** the app sends its requests to the staging backend and shows the translation it returns

#### Scenario: Changing the staging backend
- **WHEN** an owner changes the staging backend address secret and runs the build again
- **THEN** the new build talks to the new address with no change to any file in the repository

#### Scenario: Token switch on
- **WHEN** the staging backend requires an app token and the matching secret is set
- **THEN** the staging build's requests are accepted

#### Scenario: Missing backend secret
- **WHEN** the build starts and the staging backend address secret is not set
- **THEN** the run fails before building, names the missing secret, and publishes nothing

### Requirement: Plain HTTP to the staging backend only
The staging build SHALL allow plain HTTP to the staging backend's address and SHALL refuse plain HTTP to every other address, and the developer and system test builds SHALL keep their current rules.

#### Scenario: Plain HTTP staging backend
- **WHEN** the staging backend address uses plain HTTP and the staging build sends a request to it
- **THEN** the request goes through

#### Scenario: Any other plain HTTP server
- **WHEN** the staging build tries to reach any other server over plain HTTP
- **THEN** Android refuses the connection

#### Scenario: Other builds unchanged
- **WHEN** the developer or system test build is built after this change
- **THEN** it allows plain HTTP to the same local addresses as before, and to no others

### Requirement: Signed with one fixed test key
Every staging build SHALL be signed with the same test key, read with its passwords from GitHub secrets, and each build SHALL carry a higher version number than every earlier staging build.

#### Scenario: New build installs over the old one
- **WHEN** a tester has a staging build installed and installs a newer staging build
- **THEN** Android installs it as an update, and the tester does not uninstall first

#### Scenario: Missing signing secret
- **WHEN** the build starts and a signing secret is not set
- **THEN** the run fails before building, names the missing secret, and publishes nothing

### Requirement: Secrets stay out of sight
No backend address, app token, signing key or key password SHALL appear in the workflow log, in the pre-release notes or in any file committed to the repository.

#### Scenario: Build log and notes
- **WHEN** a staging build runs and publishes a pre-release
- **THEN** the workflow log and the pre-release notes contain none of the secret values

### Requirement: Setup and install guide
The repository SHALL contain a guide that lists every secret the build needs (name, what it holds, required or optional), how to create the test signing key, how to run the build by hand, and how a tester installs the app from a pre-release on a phone.

#### Scenario: Owner sets up the build
- **WHEN** an owner follows the guide on a repository with none of the build's secrets set
- **THEN** they can set every secret, run the build by hand, and get a pre-release without reading the workflow

#### Scenario: Tester installs the app
- **WHEN** a tester with access to the repository follows the guide on an Android phone
- **THEN** they can download the APK from the newest pre-release and install it

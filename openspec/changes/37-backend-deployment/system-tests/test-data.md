# System test data — backend deployment

## Loading

None. These cases need no records loaded into an environment: they exercise
servers, secrets and the workflow. The repo has no `test_data` loader, and no
loader task is opened for this epic because there are no data sets to load.
Nothing to unload.

Any test values a tester picks by hand are synthetic: throwaway strings for
`ADMIN_TOKEN`, `APP_TOKEN` and `SARVAM_API_KEY` on a test server. Never use a
real production key.

## Data sets

No data sets (no `DS-<n>`). Every case lists `Data: none`.

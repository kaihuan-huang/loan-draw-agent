# Spec: <slug>

From: `intent/<slug>.md` (accepted <date>). Author: <name>, reviewed by <product owner>. Status: draft | approved.

## Requirements
What the accepted intent requires, restated as concrete, testable statements.

## Design
How this fits the existing services (`ENGINEERING.md` layering, naming, data-access conventions). Name the files, endpoints and models that change. No implementation-level code here: that is `plan.md`, written from this spec.

## Security & compliance check
Run against `REVIEW.md`'s passes before writing this section:
- PII / contact-data / message-body handling
- Money / state impact
- §6 safety rules if this touches a confirmed user action
- Feature flag: ships default-off unless the product owner explicitly says otherwise

## Open questions / conflicts
Anywhere a policy conflicted with the request, or the intent left something unresolved. Answer these before Build starts.

---
Product owner sign-off:
- [ ] Approved as written — proceed to the build plan
- [ ] Approved with changes — listed above, re-check before Build
- [ ] Rejected — reason:

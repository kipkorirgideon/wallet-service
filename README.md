# Review: Daily Send Limits

I took a look at the structure and I think it's a good start. The `check_daily_limit`
check and the GraphQL field for headroom all make sense. However, I found a few
issues that need to be addressed before this PR can be approved.

## 1. `app/models.py` — Add a migration to manage existing and new columns

- Adding `daily_send_limit = Column(Integer, nullable=False)` changes the existing
  users table. The problem is that `Base.metadata.create_all(engine)` does not alter
  an already-created table. On an existing deployment, `SQLAlchemy` will query or
  insert a column that does not exists. Additionaly there is no backfill for existing rows.

- To fix this, write a migration that adds the column and backfills existing rows. You can
  use [Alembic](http://alembic.sqlalchemy.org) to manage migrations.

## 2. `app/schema.py` — Make the check and send atomic under concurrent requests

- `send_money` calls `limits.check_daily_limit` and `execute_transfer` as two
  separate transactions. This causes problems if two concurrent requests for the
  same sender come in at the same time: both can read the same `already_sent` total
  before either transfer's balance update commits.If both pass the check and
  proceed, it will make user's completed daily total over the limit.

- For example, a user with a 10,000 limit who fires two 8,000 sends at once could
  have both pass and succeed, landing at 16,000 sent which is well above the limit. This is
  the exact thing the feature is supposed to stop.

- To fix this, wrap the check and the write in one DB transaction with a row lock on the
  user.

## 3. Use the user's country timezone for the daily window

- `_start_of_today()` builds midnight from `datetime.utcnow()`, so the usage window
  changes at UTC midnight for every user. `CountryInfo` already carries a timezone
  field, but it is currently only used for currency lookups.
- To fix this, calculate the start of the local day from the user's country timezone instead.

## 4. Allow transfers that land exactly on the limit

- In `app/limits.py`, the comparison `already_sent + amount >= limit` rejects a
  transfer when the resulting daily total is exactly the configured limit.
- The ticket says to block only when the total would go *above* the limit.
- To fix this, change the comparison to `>`.

## 5. `app/schema.py` — Keep the status query consistent with the real check

- `daily_limit_status` sums all of today's transfers itself instead of calling
  `_amount_sent_today`, so it doesn't exclude FAILED/PENDING transfers.
- For example, a user with an 8,000 FAILED transfer and a 1,000 COMPLETED one, on a
  10,000 limit, should have 9,000 remaining per the real check. This endpoint
  reports `remaining: 1,000` instead — wrong and confusing for anyone building
  against this API.
- To fix this, call `_amount_sent_today` here instead of duplicating the filter logic `[daily_limit_status]`.

## 6. `app/limits.py` — Optimization

- `_amount_sent_today` pulls every transfer row for the day with
  `query.order_by(Transfer.created_at.desc()).all()` and sums in Python. This can
  cause latency if the endpoint gets polled a lot from the mobile app.
- To fix this, push the summation into SQLAlchemy instead of pulling rows and summing in Python.
  Also drop the `order_by` — ordering isn't needed when summing.

## Review Highlights Summary

### Recommendation: Request Changes

- The scope of this feature is appropriate, and the main use case works as
  expected.
- However, there are bugs that:
  - Let the daily limit be bypassed or misapplied.
  - Will break deployment on an existing database (migration gap).
  - Make the status endpoint disagree with the actual enforcement logic.
- I'm requesting these changes before approval.

### High Priority Issues (Must Fix Before Merge)

1. **Missing migration for the new column.**
   - `create_all` won't alter an already-created table — this will break on any
     existing deployment.
   - Since `daily_send_limit` is not nullable, there's no mechanism for backfilling
     existing rows.

2. **Race condition under concurrent requests.**
   - The check and the write aren't atomic, so concurrent sends can bypass the
     daily limit entirely.

3. **Timezone handling bug.**
   - The daily window resets at UTC midnight for every user, misattributing usage
     for non-UTC users.

4. **Transfer limit boundary validation issue.**
   - `>=` instead of `>` incorrectly blocks a transfer that lands exactly on the
     limit.

### Lower Priority

5. **Status endpoint diverges from the real check.**
   - `daily_limit_status` doesn't exclude FAILED/PENDING transfers, so it can
     report a different remaining balance than what `check_daily_limit` would
     actually allow. Not unsafe on its own, but misleading for anyone building
     against the API.

6. **Optimization.**
   - `_amount_sent_today` runs on every send and every status check. If this
     endpoint gets polled a lot from the mobile app, it'll show up as latency.

---

## What I Left Out and Why

**What I left out**
- The project didn't specify which version of Python to use.
- I found that `SQLAlchemy 2.0.30` doesn't work with `Python 3.14`.
- I had to install an older `Python 3.11` on my machine to get the project working.

**Why I left it out**
- I didn't mention this in the review because it's a problem with the project's
  setup, not something that changed in this PR.
- It would be worth creating a separate task to pin the Python version in the
  project settings, but it's unrelated to this ticket.

---

## Claude Code use

- I used Claude Code's `/code-review` command to review this diff before writing it
  up.

**Where it helped:**
- Claude found two problems on its own: the missing migration and the race
  condition.
- I already suspected the timezone bug — in a past project, users were spread
  across different timezones and we needed to harmonize them — and the tool helped
  confirm it.

**Where it fell short:**
- The boundary bug (`>=` vs `>`) and the status endpoint bug are ones it didn't
  catch; I found both myself.
- I also noticed the optimization issue, which Claude didn't catch.

**How I verified everything:**
- I set up the project on my machine and read through all the code myself to
  understand it.
- I ran the existing test suite with pytest to confirm it passed cleanly before
  digging into the diff.
- I tested the GraphQL endpoint with Postman and confirmed every finding myself.
- 

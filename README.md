# Review: Daily Send Limits

Solid first pass on the structure — `check_daily_limit`, the accumulator,
the GraphQL field for headroom, all makes sense. But there are two bugs
here that will break prod, and a few smaller ones. Don't merge until #1
and #2 are fixed. Going through each below, straight to the point.

## 1. `app/models.py` — Add a migrations to manage existing and new columns

- Adding `daily_send_limit = Column(Integer, nullable=False)` changes the existing users table, but 
`Base.metadata.create_all(engine)` does not alter an already-created table. 
- On an existing deployment the `SQL Alchemy ORM` will query or insert a column that is not present 
and there is no backfill for existing users.

- Fix: write an actual migration that adds the column and backfills existing rows. This has to land 
first — nothing else matters until it's in. Try using `https://alembic.sqlalchemy.org/en/latest/` to manage migrations.

## 2. `app/schema.py` — Make the check and send atomic under concurrent requests

- `send_money` calls `limits.check_daily_limit` and `execute_transfer` `(app/transfers.py)` as 
two separate transactions. 
- Two concurrent requests for the same sender can both read the same `already_sent` total before 
either transfer's balance update commits, so both pass the check and both proceed — taking the 
user's completed daily total over the limit.

- Example: user has a 10,000 limit, sends nothing yet, fires two 8,000
sends at once — both pass, both succeed, they've sent 16,000. This is
the exact thing the feature is supposed to stop.

- Fix: wrap the check and the write in one DB transaction with a row lock
on the user. Add a test that actually fires concurrent requests — a
normal unit test won't catch this.

## 3. Use the user's country timezone for the daily window

- `_start_of_today()` builds midnight from `datetime.utcnow()`, so the usage window changes at UTC midnight for every user. 
`CountryInfo` already carries an `IANA timezone` field `(app/countries.py)`, but it's only used for currency lookups — nothing in `limits.py` reads it. 
- For example, a Ugandan user's local-day usage between midnight and 03:00 (UTC+3) is assigned to the wrong day. 
- Please calculate the start of the current local day from `user.country's` timezone (convert to local time first. 
- Truncate to midnight then convert back to UTC for consistent storage/query comparisons), with a test around a UTC/local midnight boundary.

## 4. Allow transfers that land exactly on the limit 

- In `app/limits.py`, `already_sent + amount >= limit` rejects a transfer when the resulting daily total is exactly the configured limit. 
- The ticket says to block only when the total would go above the limit, so a user with 2,000 remaining should be able to send 2,000. 
- Please change this comparison to > and add a boundary test for an exact-limit send.

- `Fix`: change `>=` to `>`. Add a test for the exact-boundary case nothing
covers it right now.

## 5. `app/schema.py` — status endpoint disagrees with the actual check

- `daily_limit_status` sums all of today's transfers itself instead of
calling `_amount_sent_today`, so it doesn't exclude FAILED/PENDING.
- Example: user has an 8,000 FAILED transfer and a 1,000 COMPLETED one,
limit 10,000. Real check would allow 9,000 more. This endpoint reports
`remaining: 1,000`. Wrong and confusing for anyone building against
this API.

- Fix: just call `_amount_sent_today` here instead of duplicating the
filter logic.

## 6. `app/limits.py` — Optimization

- `_amount_sent_today` pulls every transfer row for the day with an
unnecessary `query.order_by(Transfer.created_at.desc()).all()` and sums in Python. 
- This Runs on every send and every status check. Fine for now but if this endpoint gets polled a lot from
the mobile app it will show up as latency. 
- Fix: push that into `SQL with SQLAlchemy` instead of pulling rows and summing in Python:

## Review Highlights Summary
### Overall Assessment
- The scope of this feature is appropriate.
- The main use case works as expected, matching the `PR_DESCRIPTION.md`.

### High Priority Issues (Must Fix Before Merge)
The following issues affect the core correctness of the daily transfer limit and should be resolved before merging:
1. Transfer limit boundary validation issue
    - Causes incorrect enforcement at the transfer limit boundary.
2. Timezone handling bug
    - Incorrectly determines which day a transfer should count toward, leading to inaccurate daily limit calculations.
3. Race condition under concurrent requests
    - Allows the daily transfer limit to be bypassed when multiple transfers are processed simultaneously.

---

## What I Left Out and Why

### What I Left Out
- The project did not specify which version of Python to use. 
- I found out that `SQLAlchemy version 2.0.30` does not work with `Python version 3.14`. 
- I had to install an older version of `Python version 3.11` on my computer to get the project working.

### Why I Left Out

- I did not mention this when I reviewed the project because it is a problem with the setup of the project not something 
that was changed in this update. 
- It would be a good idea to create a separate task to specify the Python version in the project settings but it is not 
related to the current task, about daily limits

---

## Claude Code use

- I used `Claude Code [beta]` [`/claude-review`]to review this diff before writing it up.
- It found two real problems on its own: the missing migration and the race condition.
- I already suspected the timezone bug, because in a past project I worked on, users were spread across different 
timezones and we needed to harmonize them. The tool helped confirm it.
- The boundary bug and the status endpoint bug are ones I might have missed. 
    - Nothing crashes the code just quietly gives the wrong answer. 
    - Watch for these patterns: >= vs > in limit checks, and duplicate logic that drifts from the real check.
- I set up the project on my local machine and read through all the code myself to understand it. 
    - I tested the real graphql endpoint with Postman. I confirmed every finding myself in `limits.py` and `schema.py`. 
    - I worked out the concurrency example by hand. 
    - Also noticed optimization issue which the `/claude-review` the tool didn't catch.


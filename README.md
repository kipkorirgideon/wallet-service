# Review: Daily Send Limits

I took a look at the structure and I think it is a good start. The `check_daily_limit` the check and the GraphQL field for headroom all make sense. However I found some few issues that need to be addressed before this `pr` can be approved.

## 1. `App/models.py`. Add a migration to manage existing and new columns

- When you add `daily_send_limit = Column(Integer, =False)` it changes the existing users table. The problem is that `Base.metadata.create_all(engine)` does not alter a created table. On an existing deployment the `SQLAlchemy` will Insert a column that is not present and there is no backfill for existing users.

- To fix this, you should write a migration that adds the column and backfills existing rows. You can use [Alembic](http://alembic.sqlalchemy.org) to manage migrations.

## 2. `App/schema.py`. Make the Check and Send atomic under concurrent requests

- The `send_money` function calls `limits.check_daily_limit` and `execute_transfer` as two separate transactions. This can cause problems if two concurrent requests for the sender are made at the same time. Both requests can read the `already_sent` total before either transfers balance update commits. That means both requests can pass the check and proceed. Hence user's completed daily total can go over the limit.

- For example if a user has a 10,000 limit and sends two 8,000 requests at the same time, both requests can pass the check and proceed thus 16,000 might be sent which is above the limit. This is the exact thing the feature is supposed to stop.

- To fix this, you should wrap the check and the write in one DB transaction with a row lock on the user.

## 3. Use the users country timezone for the window

- The `_start_of_today()` function builds midnight from `datetime.utcnow()` so the usage window changes at UTC midnight for every user. However the `CountryInfo` already carries a timezone field but it is only used for currency lookups. You should calculate the start of the local day from the users country timezone.

## 4. Allow transfers that land on the limit

- In `app/limits.py` the comparison `already_sent + amount >= limit` rejects a transfer when the resulting daily total is exactly the configured limit.
- However the ticket says to block when the total would go above the limit.
- To fix this, you should change this comparison to `>`.

## 5. `App/schema.py`. Status endpoint disagrees with the check

- The `daily_limit_status` sums all of todays transfers itself instead of calling `_amount_sent_today`. This means it does not exclude FAILED/PENDING transfers. For example if a user has an 8,000 transfer and a 1,000 COMPLETED one with a limit of 10,000, the real check would allow 9,000 more. However the endpoint reports `remaining: 1,000` which is wrong and confusing.

- To fix this, you should call `_amount_sent_today` instead of duplicating the filter logic.

## 6. `App/limits.py`. Optimization

- The `_amount_sent_today` function pulls every transfer row for the day with a `query.order_by(Transfer.created_at.desc()).all()` and sums in Python. This can cause latency if the endpoint gets polled a lot from the mobile app.
- To fix this, push the summation into SQL with `SQLAlchemy` instead of pulling rows and summing in Python..
- Also drop the `order_by` too. Ordering is not needed when doing summation.

## Review Highlights Summary

### Recommendation: Request Changes

- The scope of this feature is appropriate. The main use case works as expected.
- However there are a bugs that:
  - Let the daily limit be bypassed or misapplied
  - Will break deployment on an existing database - `migration gap`
- I am requesting these changes `BEFORE` approval

### High Priority Issues (Must Fix Before Merge)

1. **Missing migration for the column**.
   - `create_all` won't alter an already created table.This will break on any existing deployment
   - Since `send_daily_limit` is not nullable there is no mechanism for backfilling existing users and current users.

2. **Concurrent requests Issue**.
   - The check and the write aren't atomic, so concurrent sends can bypass the daily limit entirely.

3. **Timezone handling bug**.
   - The daily window resets at UTC midnight for every user

4. **Transfer limit boundary validation issue**.
   - `>=` Of `>` incorrectly blocks a transfer that lands exactly on the limit.

### Lower Priority

5. **Optimization**
   - `_amount_sent_today` pulls every transfer row for the day with an unnecessary `query.order_by(Transfer.created_at.desc()).all()` and sums in Python.
   - This runs on every send and every status check. If this endpoint gets polled a lot from the mobile app it will show up as latency.
   
---

## What I Left Out and Why
**What I Left Out**
- The project did not specify which version of Python to use.
- I found out that SQLAlchemy version 2.0.30 does not work with Python version 3.14.
- I had to install an older version of Python version 3.11 on my computer to get the project working.
  
**Why I Left Out**
- I did not mention this when I reviewed the project because it is a problem with the setup of the project not something that was changed in this update.
- It would be a good idea to create a separate task to specify the Python version in the project settings but it is not related to the current task, about daily limits

---

## Claude Code use

- I used Claude Code `[/code-review]` command to review this diff before writing it up.

**Where it helped:**
- It found two problems on its own:
  - Missing migrations
  - the race condition.
- I already suspected the timezone bug — in a past project, users were spread across
  different timezones and we needed to harmonize them and the tool helped confirm it.

**Where it fell short:**
- The boundary bug for daily send limit
- I also noticed an optimization issue that it didn't catch.

**How I verified everything:**
- I set up the project on my machine and read through all the code myself to
  understand it.
- I tested the GraphQL endpoint with Postman and confirmed every finding myself.

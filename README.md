# Review: Daily Send Limits

I took a look at the structure and I think it is a good start. The `check_daily_limit` the check and the GraphQL field for headroom all make sense. However I found a problems that need to be fixed before this can be merged.

## 1. `App/models.py`. Add a migration to manage existing and new columns

- When you add `daily_send_limit = Column(Integer, =False)` it changes the existing users table. The problem is that `Base.metadata.create_all(engine)` does not alter a created table. On an existing deployment the `SQLAlchemy` will Insert a column that is not present and there is no backfill for existing users.

- To fix this you should write a migration that adds the column and backfills existing rows. You can use Alembic to manage migrations.

## 2. `App/schema.py`. Make the check. Send atomic under concurrent requests

- The `send_money` function calls `limits.check_daily_limit` and `execute_transfer` as two separate transactions. This can cause problems if two concurrent requests for the sender are made at the same time. Both requests can read the already_sent` total before either transfers balance update commits so both requests can pass the check and proceed. This means the users completed daily total can go over the limit.

- For example if a user has a 10,000 limit and sends two 8,000 requests at the time both requests can pass the check and proceed. This is the thing the feature is supposed to stop.

- To fix this you should wrap the check and the write in one DB transaction with a row lock on the user. You should also add a test that fires requests.

## 3. Use the users country timezone for the window

- The `_start_of_today()` function builds midnight from `datetime.utcnow()` so the usage window changes at UTC midnight for every user. However the `CountryInfo` already carries a timezone field but it is only used for currency lookups. You should calculate the start of the local day from the users country timezone.

- For example a Ugandan users local-day usage between midnight and 03:00 (UTC+3) is assigned to the day. You should convert to time first truncate to midnight and then convert back to UTC for consistent storage and query comparisons. You should also add a test around a UTC/ midnight boundary.

## 4. Allow transfers that land on the limit

- In `app/limits.py` the comparison `already_sent + amount >= limit` rejects a transfer when the resulting daily total is exactly the configured limit. However the ticket says to block when the total would go above the limit. You should change this comparison to `>`.

## 5. `App/schema.py`. Status endpoint disagrees with the check

- The `daily_limit_status` sums all of todays transfers itself instead of calling `_amount_sent_today`. This means it does not exclude FAILED/PENDING transfers. For example if a user has an 8,000 transfer and a 1,000 COMPLETED one with a limit of 10,000 the real check would allow 9,000 more. However the endpoint reports `remaining: 1,000` which is wrong and confusing.

- To fix this you should call `_amount_sent_today` of duplicating the filter logic.

## 6. `App/limits.py`. Optimization

- The `_amount_sent_today` function pulls every transfer row for the day with a query.order_by(Transfer.created_at.desc()).all()` and sums in Python. This can cause latency if the endpoint gets polled a lot from the app. You should push this into SQL with SQLAlchemy of pulling rows and summing in Python.

## Review Highlights Summary

### Recommendation: Request Changes

- The scope of this feature is appropriate. The main use case works as expected. However there are a bugs that let the daily limit be bypassed or misapplied, plus a migration gap that will break deployment on an existing database. I am requesting changes than approving as it is.

### High Priority Issues (Must Fix Before Merge)

1. **Missing migration for the column**. `Create_all` won't alter an already-created table so this breaks on any existing deployment with no backfill for current users.

2. **Race condition under requests**. The check and the write aren't atomic so concurrent sends can bypass the daily limit entirely.

3. **Timezone handling bug**. The daily window resets at UTC midnight for everyone so usage gets attributed to the day for non-UTC users.

4. **Transfer limit boundary validation issue**. `>=` Of `>` incorrectly blocks a transfer that lands exactly on the limit.

### Lower Priority

5. Status endpoint diverges from the real enforcement logic (not unsafe on its own but should still be fixed before merge since it misleads anyone building against the API).

6. Optimization: sum in SQL of Python (not blocking, but worth doing before this endpoint sees real traffic).

## What I Left Out. Why

- I did not mention the Python version issue when I reviewed the project because it is a problem with the setup of the project, not something that was changed in this update. It would be an idea to create a separate task to specify the Python version in the project settings but it is not related to the current task about daily limits.

## Claude Code use

- I used Claude Code to review this diff before writing it up. It found two problems on its own i.e the missing migration and the race condition.
- I already suspected the timezone bug because in a project I worked on users were spread across different timezones and we needed to harmonize them. The tool helped confirm it.
- The boundary bug and the status endpoint bug are ones I might have missed.
- I set up the project on my machine and read through all the code myself to understand it. I tested the GraphQL endpoint, with Postman and confirmed every finding myself
- I also noticed an optimization issue that the Claude Code did not catch.

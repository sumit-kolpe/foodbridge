# FoodBridge API server

This is the REST API for FoodBridge, built with **Node.js + Express + PostgreSQL** (`pg`). It has 19 routes: one for each of the 12 Milestone 3 queries, plus 7 auxiliary routes. The full specification is in [`docs/milestones/M4_API_Specification.pdf`](../docs/milestones/M4_API_Specification.pdf).

## Run it

```bash
cd server
npm install
cp .env.example .env        # then fill in the RDS host, user and password
npm start                   # http://localhost:8080
```

In another terminal:

```bash
npm run smoke               # calls every read route, prints PASS/FAIL + timings
npm run smoke -- --write    # also tests POST/PATCH (adds a few test rows to the DB)
```

Check that the API can reach the database: `curl http://localhost:8080/health`

## Layout

| File | Purpose |
|---|---|
| `src/server.js` | Entry point (starts the HTTP server) |
| `src/app.js` | Express app: middleware, route mounting, 404 + error handler, `/health` |
| `src/config.js` | Settings from `.env`; the app clock (`now()`) |
| `src/db.js` | `pg` connection pool, `query()` and `transaction()` helpers, type parsing |
| `src/http.js` | Parameter validation (`int`, `oneOf`, `zip`, `timestamp`, `month`) and error types |
| `src/queries.js` | **All SQL**: Q1–Q12 (parameterized Milestone 3 queries) + auxiliary statements |
| `src/routes/organizations.js` | `GET /organizations` (Q1), `GET /organizations/:id`, `GET /organizations/:id/donation-summary` (Q3) |
| `src/routes/donations.js` | `GET /donations/available` (Q2), `POST /donations` |
| `src/routes/requests.js` | `POST /requests`, `GET /requests/:id/allocations` (Q4) |
| `src/routes/allocations.js` | `POST /allocations`, `PATCH /allocations/:id/status` (transactions with row locks) |
| `src/routes/analytics.js` | `GET /dashboard/kpis` (Q5), `GET /categories`, `GET /categories/demand` (Q6), `GET /analytics/*` (Q7–Q12) |
| `scripts/smoke-test.js` | End-to-end check of every route |

## Design notes

- **Parameterized SQL only.** User input is passed as `$1, $2, …`, never concatenated into SQL, which prevents SQL injection.
- **Validation first.** Every parameter is checked for type, range and allowed values before any query runs. Bad input returns `400` with a message saying what is wrong.
- **App clock.** The dataset is a snapshot taken at `AS_OF = 2026-11-10 12:00:00`. The API's "now" starts at that moment and advances in real time while the server runs, so "available donations" and "last 14 days" stay meaningful.
- **No over-allocation.** `POST /allocations` locks the donation and request rows (`SELECT … FOR UPDATE`) inside a transaction. It checks the category, deadlines, remaining servings and outstanding need, then inserts the allocation and recomputes both statuses. Two simultaneous claims cannot over-allocate.
- **Status transitions.** Allocations move `pending → confirmed → picked_up → delivered`. They can also be `cancelled` from `pending` or `confirmed`. Any other change returns `409`.
- **Response format.** Successful responses are `{ "data": …, "meta": { … } }`. Errors are `{ "error": { "code", "message", "details"? } }`.

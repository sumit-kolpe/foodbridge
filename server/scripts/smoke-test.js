// Calls every API route and prints status, row count and time.
//   node scripts/smoke-test.js            read-only routes
//   node scripts/smoke-test.js --write    also creates a donation, a request and an
//                                         allocation, and walks it to 'delivered'
//                                         (adds a few rows to the database)
// BASE_URL defaults to http://localhost:8080
const BASE = process.env.BASE_URL || 'http://localhost:8080';
const WRITE = process.argv.includes('--write');
let failures = 0;

async function call(method, path, body, expectStatus) {
  const t0 = Date.now();
  const res = await fetch(BASE + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await res.json().catch(() => ({}));
  const ms = Date.now() - t0;
  const ok = expectStatus ? res.status === expectStatus : res.ok;
  if (!ok) failures += 1;
  const size = Array.isArray(json.data) ? `${json.data.length} rows` : json.error ? json.error.message : 'object';
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${res.status}  ${String(ms).padStart(6)} ms  ${method.padEnd(5)} ${path}  -> ${size}`);
  return json;
}

(async () => {
  console.log(`Testing ${BASE}\n`);
  await call('GET', '/health');

  // ---- the 12 query routes ----
  const orgs = await call('GET', '/organizations?role=recipient&status=active&search=church&page_size=5');
  await call('GET', '/donations/available?limit=10');
  await call('GET', '/organizations/400/donation-summary');
  await call('GET', '/requests/100006/allocations');
  await call('GET', '/dashboard/kpis');
  await call('GET', '/categories/demand?days=30');
  await call('GET', '/analytics/monthly-fulfillment?from=2026-01&to=2026-10&category_id=1');
  await call('GET', '/analytics/donor-leaderboard?min_donations=20&limit=10');
  await call('GET', '/analytics/zip-gaps?limit=10');
  await call('GET', '/analytics/avoidable-loss?days=14&limit=10');
  await call('GET', '/analytics/fully-served-recipients?days=180');
  await call('GET', '/analytics/unmet-demand?days=14');

  // ---- auxiliary reads ----
  await call('GET', '/categories');
  if (orgs.data && orgs.data[0]) await call('GET', `/organizations/${orgs.data[0].organization_id}`);

  // ---- error handling ----
  await call('GET', '/organizations?zip=abc', null, 400);
  await call('GET', '/organizations/999999', null, 404);
  await call('GET', '/analytics/avoidable-loss?days=0', null, 400);

  if (WRITE) {
    console.log('\nWrite flow (creates test rows):');
    const kpis = await call('GET', '/health');
    const now = kpis.as_of;
    const plus = (h) => new Date(Date.parse(now.replace(' ', 'T') + 'Z') + h * 3600e3)
      .toISOString().slice(0, 19).replace('T', ' ');
    const donors = await call('GET', '/organizations?role=donor&status=active&page_size=1');
    const recips = await call('GET', '/organizations?role=recipient&status=active&page_size=1');
    const donorId = donors.data[0].organization_id;
    const recipId = recips.data[0].organization_id;

    const don = await call('POST', '/donations', {
      donor_org_id: donorId, category_id: 1, quantity: 40,
      expires_at: plus(24), pickup_deadline: plus(6),
    }, 201);
    const rq = await call('POST', '/requests', {
      recipient_org_id: recipId, category_id: 1, requested_quantity: 30, needed_by: plus(12),
    }, 201);
    await call('POST', '/allocations',
      { donation_id: don.data.donation_id, request_id: rq.data.request_id, quantity: 50 }, 409);
    const al = await call('POST', '/allocations',
      { donation_id: don.data.donation_id, request_id: rq.data.request_id, quantity: 30 }, 201);
    const id = al.data.allocation_id;
    await call('PATCH', `/allocations/${id}/status`, { status: 'delivered' }, 409);
    await call('PATCH', `/allocations/${id}/status`, { status: 'confirmed' });
    await call('PATCH', `/allocations/${id}/status`, { status: 'picked_up' });
    const done = await call('PATCH', `/allocations/${id}/status`, { status: 'delivered' });
    console.log('   final statuses:', JSON.stringify(done.meta));
    await call('GET', `/requests/${rq.data.request_id}/allocations`);
  }

  console.log(`\n${failures === 0 ? 'All checks passed.' : `${failures} check(s) failed.`}`);
  process.exit(failures ? 1 : 0);
})().catch((e) => {
  console.error('Could not reach the API:', e.message);
  process.exit(1);
});

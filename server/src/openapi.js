// OpenAPI 3.0 description of the FoodBridge API, served at /openapi.json and
// rendered by Swagger UI at /docs (like FastAPI's /docs page).

// ---------- small builders ----------
const qp = (name, schema, description, example) =>
  ({ name, in: 'query', required: false, schema, description, ...(example !== undefined ? { example } : {}) });
const pp = (name, description, example) =>
  ({ name, in: 'path', required: true, schema: { type: 'integer', minimum: 1 }, description, example });
const int = (extra = {}) => ({ type: 'integer', ...extra });
const str = (extra = {}) => ({ type: 'string', ...extra });
const num = (extra = {}) => ({ type: 'number', ...extra });
const ts = (description) => ({ type: 'string', example: '2026-11-10T12:00:00', description });
const tsNull = (description) => ({ type: 'string', nullable: true, example: '2026-11-10T14:30:00', description });
const ref = (name) => ({ $ref: `#/components/schemas/${name}` });
const obj = (properties) => ({ type: 'object', properties });

/** 200 response whose body is { data: <data>, meta: <meta> } */
const ok = (description, data, meta) => ({
  description,
  content: { 'application/json': { schema: obj({ data, ...(meta ? { meta: obj(meta) } : {}) }) } },
});
const list = (item) => ({ type: 'array', items: item });
const err = (description) => ({ description, content: { 'application/json': { schema: ref('Error') } } });
const E400 = err('Invalid or missing parameter');
const E404 = err('Not found');
const E409 = err('Business rule violated');

const asOf = { as_of: ts('API clock used as "now"') };

// ---------- reusable schemas ----------
const schemas = {
  Error: obj({
    error: obj({
      code: str({ enum: ['BAD_REQUEST', 'NOT_FOUND', 'CONFLICT', 'INTERNAL_ERROR'], example: 'BAD_REQUEST' }),
      message: str({ example: "'zip' must be a 5-digit ZIP code" }),
      details: { type: 'object', nullable: true, additionalProperties: true },
    }),
  }),
  Organization: obj({
    organization_id: int({ example: 178, description: '1-346 real Philadelphia sites, 347+ synthetic' }),
    organization_name: str({ example: 'Hickman Temple Daycare' }),
    organization_type: str({ enum: ['donor', 'recipient', 'both'] }),
    address: str({ example: '1220 S. 58th St' }),
    city: str({ example: 'Philadelphia' }),
    zip_code: str({ nullable: true, example: '19143' }),
    contact_information: str({ nullable: true, example: '(215) 555-0100' }),
    status: str({ enum: ['active', 'inactive'] }),
  }),
  Category: obj({
    category_id: int({ example: 1 }),
    category_name: str({ example: 'Prepared Hot Meals' }),
    storage_type: str({ enum: ['refrigerated', 'frozen', 'shelf-stable', 'other'] }),
    description: str(),
  }),
  Donation: obj({
    donation_id: int({ example: 150001 }),
    donor_org_id: int({ example: 400 }),
    category_id: int({ example: 1 }),
    quantity: int({ example: 40 }),
    donated_at: ts('Posted at (API clock)'),
    expires_at: ts('Expiry'),
    pickup_deadline: ts('Latest pickup time'),
    status: str({ enum: ['available', 'partially_allocated', 'fully_allocated', 'expired', 'cancelled'] }),
  }),
  Request: obj({
    request_id: int({ example: 120001 }),
    recipient_org_id: int({ example: 178 }),
    category_id: int({ example: 1 }),
    requested_quantity: int({ example: 30 }),
    requested_at: ts('Posted at (API clock)'),
    needed_by: ts('Deadline'),
    status: str({ enum: ['open', 'partially_fulfilled', 'fulfilled', 'expired', 'cancelled'] }),
  }),
  Allocation: obj({
    allocation_id: int({ example: 198416 }),
    donation_id: int({ example: 150001 }),
    request_id: int({ example: 120001 }),
    quantity_allocated: int({ example: 30 }),
    allocated_at: ts('When the allocation was made'),
    status: str({ enum: ['pending', 'confirmed', 'picked_up', 'delivered', 'cancelled'] }),
    picked_up_at: tsNull('Set when status becomes picked_up'),
    delivered_at: tsNull('Set when status becomes delivered'),
  }),
  StatusMeta: obj({
    donation_status: str({ example: 'partially_allocated' }),
    request_status: str({ example: 'partially_fulfilled' }),
  }),
};

const days = (def, max) => qp('days', int({ minimum: 1, maximum: max, default: def }), `Window length in days (1-${max})`);
const limit = (def, max) => qp('limit', int({ minimum: 1, maximum: max, default: def }), `Maximum rows (1-${max})`);
const categoryFilter = qp('category_id', int({ minimum: 1 }), 'Only this food category (omit for all)');

// ---------- paths ----------
const paths = {
  '/health': {
    get: {
      tags: ['Auxiliary'], summary: 'API and database status (A1)',
      responses: {
        200: { description: 'Connected', content: { 'application/json': { schema: obj({
          status: str({ example: 'ok' }), database: str({ example: 'connected' }),
          organizations: int({ example: 1000 }), ...asOf }) } } },
        503: { description: 'Database unreachable' },
      },
    },
  },

  '/organizations': {
    get: {
      tags: ['Organizations'], summary: 'Search the organization directory (R1 / Q1)',
      description: 'Filters by role, status, ZIP code and name; alphabetical; paginated.',
      parameters: [
        qp('role', str({ enum: ['donor', 'recipient'] }), 'donor or recipient (type "both" matches either)'),
        qp('status', str({ enum: ['active', 'inactive'] }), 'Organization status'),
        qp('zip', str({ pattern: '^\\d{5}$' }), '5-digit ZIP code', '19140'),
        qp('search', str({ maxLength: 100 }), 'Case-insensitive part of the name', 'church'),
        qp('page', int({ minimum: 1, default: 1 }), 'Page number'),
        qp('page_size', int({ minimum: 1, maximum: 100, default: 20 }), 'Rows per page'),
      ],
      responses: {
        200: ok('Matching organizations', list(ref('Organization')), {
          page: int(), page_size: int(), total: int(), total_pages: int() }),
        400: E400,
      },
    },
  },

  '/organizations/{id}': {
    get: {
      tags: ['Organizations'], summary: 'Get one organization (A3)',
      parameters: [pp('id', 'Organization id', 178)],
      responses: { 200: ok('The organization', ref('Organization')), 400: E400, 404: E404 },
    },
  },

  '/organizations/{id}/donation-summary': {
    get: {
      tags: ['Organizations'], summary: 'Donor profile by food category (R3 / Q3)',
      parameters: [pp('id', 'Organization id (a donor)', 400)],
      responses: {
        200: ok('Donations per category', list(obj({
          category_id: int(), category_name: str(), donations: int(),
          servings_donated: int(), avg_servings: num() })), {
          organization_id: int(), organization_name: str(),
          total_donations: int(), total_servings_donated: int() }),
        400: E400, 404: E404,
      },
    },
  },

  '/donations/available': {
    get: {
      tags: ['Donations'], summary: 'Donations that can still be claimed (R2 / Q2)',
      description: 'Available or partially allocated donations whose pickup deadline has not passed, soonest deadline first.',
      parameters: [categoryFilter, limit(50, 200)],
      responses: {
        200: ok('Claimable donations', list(obj({
          donation_id: int(), donor_org_id: int(), donor: str(), donor_zip: str({ nullable: true }),
          category_id: int(), category_name: str(), storage_type: str(),
          quantity: int(), remaining_servings: int({ description: 'Servings not yet allocated' }),
          donated_at: ts(), pickup_deadline: ts(), expires_at: ts(), status: str() })),
        { ...asOf, count: int() }),
        400: E400,
      },
    },
  },

  '/donations': {
    post: {
      tags: ['Donations'], summary: 'Post surplus food (A4)',
      description: 'donated_at is set to the API clock; the organization must be an active donor (or both).',
      requestBody: {
        required: true,
        content: { 'application/json': {
          schema: { type: 'object', required: ['donor_org_id', 'category_id', 'quantity', 'expires_at', 'pickup_deadline'],
            properties: {
              donor_org_id: int({ minimum: 1 }), category_id: int({ minimum: 1 }),
              quantity: int({ minimum: 1, maximum: 100000 }),
              expires_at: str({ description: 'Future timestamp' }),
              pickup_deadline: str({ description: 'Between now and expires_at' }) } },
          example: { donor_org_id: 400, category_id: 1, quantity: 40,
            expires_at: '2026-11-11 12:00:00', pickup_deadline: '2026-11-10 18:00:00' },
        } },
      },
      responses: { 201: ok('Created', ref('Donation')), 400: E400, 404: E404, 409: E409 },
    },
  },

  '/requests': {
    post: {
      tags: ['Requests'], summary: 'Post a food request (A5)',
      description: 'requested_at is set to the API clock; the organization must be an active recipient (or both).',
      requestBody: {
        required: true,
        content: { 'application/json': {
          schema: { type: 'object', required: ['recipient_org_id', 'category_id', 'requested_quantity', 'needed_by'],
            properties: {
              recipient_org_id: int({ minimum: 1 }), category_id: int({ minimum: 1 }),
              requested_quantity: int({ minimum: 1, maximum: 100000 }),
              needed_by: str({ description: 'Not in the past' }) } },
          example: { recipient_org_id: 178, category_id: 1, requested_quantity: 30, needed_by: '2026-11-11 00:00:00' },
        } },
      },
      responses: { 201: ok('Created', ref('Request')), 400: E400, 404: E404, 409: E409 },
    },
  },

  '/requests/{id}/allocations': {
    get: {
      tags: ['Requests'], summary: 'Track the allocations of a request (R4 / Q4)',
      parameters: [pp('id', 'Request id', 100006)],
      responses: {
        200: ok('Allocations for the request', list(obj({
          allocation_id: int(), donation_id: int(), donor_org_id: int(), donor: str(),
          quantity_allocated: int(), status: str(), allocated_at: ts(),
          picked_up_at: tsNull(), delivered_at: tsNull() })), {
          request: ref('Request'), servings_allocated: int(), servings_delivered: int() }),
        400: E400, 404: E404,
      },
    },
  },

  '/allocations': {
    post: {
      tags: ['Allocations'], summary: 'Allocate servings of a donation to a request (A6)',
      description: 'Runs in a transaction with row locks. Fails with 409 if the categories differ, a deadline has passed, '
        + 'or the quantity exceeds the donation\'s remaining servings or the request\'s outstanding need.',
      requestBody: {
        required: true,
        content: { 'application/json': {
          schema: { type: 'object', required: ['donation_id', 'request_id', 'quantity'],
            properties: { donation_id: int({ minimum: 1 }), request_id: int({ minimum: 1 }), quantity: int({ minimum: 1 }) } },
          example: { donation_id: 150001, request_id: 120001, quantity: 30 },
        } },
      },
      responses: { 201: ok('Created (status pending)', ref('Allocation'), schemas.StatusMeta.properties),
        400: E400, 404: E404, 409: E409 },
    },
  },

  '/allocations/{id}/status': {
    patch: {
      tags: ['Allocations'], summary: 'Advance pickup / delivery status (A7)',
      description: 'pending -> confirmed -> picked_up -> delivered; pending or confirmed -> cancelled.',
      parameters: [pp('id', 'Allocation id', 198416)],
      requestBody: {
        required: true,
        content: { 'application/json': {
          schema: { type: 'object', required: ['status'],
            properties: { status: str({ enum: ['confirmed', 'picked_up', 'delivered', 'cancelled'] }) } },
          example: { status: 'confirmed' },
        } },
      },
      responses: { 200: ok('Updated', ref('Allocation'), schemas.StatusMeta.properties),
        400: E400, 404: E404, 409: E409 },
    },
  },

  '/categories': {
    get: {
      tags: ['Categories'], summary: 'List food categories (A2)',
      responses: { 200: ok('All categories', list(ref('Category'))) },
    },
  },

  '/categories/demand': {
    get: {
      tags: ['Categories'], summary: 'Demand per category over the last N days (R6 / Q6)',
      parameters: [days(30, 730)],
      responses: {
        200: ok('Requests per category', list(obj({
          category_id: int(), category_name: str(), storage_type: str(),
          requests: int(), servings_requested: int() })), { ...asOf, days: int() }),
        400: E400,
      },
    },
  },

  '/dashboard/kpis': {
    get: {
      tags: ['Dashboard'], summary: 'Headline numbers (R5 / Q5)',
      responses: {
        200: ok('KPIs', obj({
          total_allocations: int(), delivered_allocations: int(), servings_delivered: int(),
          servings_in_transit: int(), cancelled_allocations: int() }), asOf),
      },
    },
  },

  '/analytics/monthly-fulfillment': {
    get: {
      tags: ['Analytics'], summary: 'Monthly supply vs. demand vs. delivered (R7 / Q7, complex)',
      parameters: [
        categoryFilter,
        qp('from', str({ pattern: '^\\d{4}-\\d{2}$', default: '2025-01' }), 'First month (YYYY-MM)', '2026-01'),
        qp('to', str({ pattern: '^\\d{4}-\\d{2}$' }), 'Last month (YYYY-MM); default = current month', '2026-10'),
      ],
      responses: {
        200: ok('One row per month and category', list(obj({
          month: str({ example: '2026-03' }), category_id: int(), category_name: str(),
          servings_donated: int(), servings_requested: int(), servings_delivered: int(),
          demand_met_pct: num({ nullable: true }) })), { from: str(), to: str(), category_id: int({ nullable: true }) }),
        400: E400,
      },
    },
  },

  '/analytics/donor-leaderboard': {
    get: {
      tags: ['Analytics'], summary: 'Donor performance ranking (R8 / Q8, complex)',
      parameters: [qp('min_donations', int({ minimum: 1, default: 20 }), 'Minimum donations to be ranked'), limit(25, 500)],
      responses: {
        200: ok('Ranked donors', list(obj({
          rank_by_delivered: int(), organization_id: int(), organization_name: str(), zip_code: str({ nullable: true }),
          donations: int(), servings_donated: int(), servings_delivered: int(),
          delivery_rate_pct: num(), vs_platform_pct_points: num() })), { min_donations: int(), limit: int() }),
        400: E400,
      },
    },
  },

  '/analytics/zip-gaps': {
    get: {
      tags: ['Analytics'], summary: 'Unmet need by ZIP code (R9 / Q9, complex)',
      parameters: [limit(50, 100)],
      responses: {
        200: ok('ZIP codes ranked by unmet need per site', list(obj({
          gap_rank: int(), zip_code: str(), unmet_servings: int(), unmet_requests: int(),
          active_recipient_sites: int(), servings_donated_locally: int(), unmet_per_site: num() })), { limit: int() }),
        400: E400,
      },
    },
  },

  '/analytics/avoidable-loss': {
    get: {
      tags: ['Analytics'], summary: 'Avoidable food loss (R10 / Q10, complex, slow before tuning: ~2 min on RDS)',
      parameters: [days(14, 90), limit(25, 200)],
      responses: {
        200: ok('Lost servings per category and donor', list(obj({
          category_id: int(), category_name: str(), donor_org_id: int(), donor: str(),
          avoidable_expired_donations: int(), avoidable_lost_servings: int() })), { ...asOf, days: int(), limit: int() }),
        400: E400,
      },
    },
  },

  '/analytics/fully-served-recipients': {
    get: {
      tags: ['Analytics'], summary: 'Recipients served in every category they requested (R11 / Q11, complex)',
      parameters: [days(180, 730)],
      responses: {
        200: ok('Fully served recipients', list(obj({
          organization_id: int(), organization_name: str(), zip_code: str({ nullable: true }),
          categories_requested: int(), requests: int(), servings_received: int({ nullable: true }) })),
        { ...asOf, days: int(), count: int() }),
        400: E400,
      },
    },
  },

  '/analytics/unmet-demand': {
    get: {
      tags: ['Analytics'], summary: 'Structurally unmet demand (R12 / Q12, complex, slow before tuning: ~3 min on RDS)',
      parameters: [days(14, 90)],
      responses: {
        200: ok('Shortfall per category', list(obj({
          category_id: int(), category_name: str(), unmeetable_requests: int(),
          recipients_affected: int(), total_shortfall_servings: int() })), { ...asOf, days: int() }),
        400: E400,
      },
    },
  },
};

module.exports = function buildOpenApi(serverUrl) {
  return {
    openapi: '3.0.3',
    info: {
      title: 'FoodBridge API',
      version: '1.0.0',
      description: 'CIS 5500 Group 25 - food rescue platform for Philadelphia. 19 routes: one per Milestone 3 query '
        + '(R1-R12) plus 7 auxiliary routes. Times are "YYYY-MM-DD HH:MM:SS"; the API clock starts at the data '
        + 'snapshot 2026-11-10 12:00:00. POST/PATCH calls change the database.',
    },
    servers: [{ url: serverUrl, description: 'This server' }],
    tags: [
      { name: 'Organizations' }, { name: 'Donations' }, { name: 'Requests' }, { name: 'Allocations' },
      { name: 'Categories' }, { name: 'Dashboard' }, { name: 'Analytics', description: 'Complex queries Q7-Q12' },
      { name: 'Auxiliary' },
    ],
    paths,
    components: { schemas },
  };
};

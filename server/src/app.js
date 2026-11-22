// Express application: middleware, route mounting, error handling.
const express = require('express');
const cors = require('cors');
const db = require('./db');
const config = require('./config');
const { ApiError } = require('./http');
const { dashboard, categories, analytics } = require('./routes/analytics');

const app = express();
app.use(cors());
app.use(express.json());

// ---------- Interactive API docs (Swagger UI, like FastAPI's /docs) ----------
const openapi = require('./openapi')('/');
app.get('/openapi.json', (req, res) => res.json(openapi));

const SWAGGER_UI = 'https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14';
const docsPage = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FoodBridge API - Swagger UI</title>
  <link rel="stylesheet" href="${SWAGGER_UI}/swagger-ui.css">
  <style>body { margin: 0; } .topbar { display: none; }</style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="${SWAGGER_UI}/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({
      url: '/openapi.json',
      dom_id: '#swagger-ui',
      deepLinking: true,
      docExpansion: 'list',
      defaultModelsExpandDepth: 0,
      displayRequestDuration: true,   // shows how long each call took
      tryItOutEnabled: true,          // "Try it out" open by default, like FastAPI
      persistAuthorization: false,
    });
  </script>
</body>
</html>`;
app.get('/docs', (req, res) => res.set('Content-Type', 'text/html; charset=utf-8').send(docsPage));

// GET /  - index of all routes (handy in the browser during demos)
app.get('/', (req, res) => {
  res.json({
    name: 'FoodBridge API',
    docs: '/docs (Swagger UI)  |  /openapi.json (OpenAPI 3 spec)',
    as_of: config.now(),
    routes: [
      'GET    /health',
      'GET    /organizations?role=&status=&zip=&search=&page=&page_size=      (Q1)',
      'GET    /organizations/:id',
      'GET    /organizations/:id/donation-summary                              (Q3)',
      'GET    /donations/available?category_id=&limit=                         (Q2)',
      'POST   /donations',
      'POST   /requests',
      'GET    /requests/:id/allocations                                        (Q4)',
      'POST   /allocations',
      'PATCH  /allocations/:id/status',
      'GET    /categories',
      'GET    /categories/demand?days=                                         (Q6)',
      'GET    /dashboard/kpis                                                  (Q5)',
      'GET    /analytics/monthly-fulfillment?category_id=&from=&to=            (Q7)',
      'GET    /analytics/donor-leaderboard?min_donations=&limit=               (Q8)',
      'GET    /analytics/zip-gaps?limit=                                       (Q9)',
      'GET    /analytics/avoidable-loss?days=&limit=                           (Q10)',
      'GET    /analytics/fully-served-recipients?days=                         (Q11)',
      'GET    /analytics/unmet-demand?days=                                    (Q12)',
    ],
  });
});

// GET /health  (auxiliary) - API and database status
app.get('/health', async (req, res) => {
  try {
    const [row] = await db.query('SELECT COUNT(*) AS organizations FROM Organization');
    res.json({ status: 'ok', database: 'connected', organizations: row.organizations, as_of: config.now() });
  } catch (err) {
    res.status(503).json({ status: 'error', database: 'unreachable', message: err.message });
  }
});

app.use('/organizations', require('./routes/organizations'));
app.use('/donations', require('./routes/donations'));
app.use('/requests', require('./routes/requests'));
app.use('/allocations', require('./routes/allocations'));
app.use('/categories', categories);
app.use('/dashboard', dashboard);
app.use('/analytics', analytics);

// Unknown route
app.use((req, res) => {
  res.status(404).json({ error: { code: 'NOT_FOUND', message: `No route ${req.method} ${req.path}` } });
});

// Error handler: ApiError -> its status; malformed JSON -> 400; anything else -> 500
// eslint-disable-next-line no-unused-vars
app.use((err, req, res, next) => {
  if (err instanceof ApiError) {
    return res.status(err.status).json({
      error: { code: err.code, message: err.message, ...(err.details ? { details: err.details } : {}) },
    });
  }
  if (err.type === 'entity.parse.failed') {
    return res.status(400).json({ error: { code: 'BAD_REQUEST', message: 'Request body is not valid JSON' } });
  }
  console.error(err);
  res.status(500).json({ error: { code: 'INTERNAL_ERROR', message: 'Unexpected server error' } });
});

module.exports = app;

// Organizations page: directory search, organization detail, donor summary.
const router = require('express').Router();
const db = require('../db');
const Q = require('../queries');
const { wrap, int, oneOf, text, zip, notFound } = require('../http');

// GET /organizations  (Q1) - search the organization directory
router.get('/', wrap(async (req, res) => {
  const role = oneOf(req.query.role, 'role', ['donor', 'recipient']);
  const status = oneOf(req.query.status, 'status', ['active', 'inactive']);
  const zipCode = zip(req.query.zip);
  const search = text(req.query.search, 'search', { max: 100 });
  const page = int(req.query.page, 'page', { def: 1, min: 1 });
  const pageSize = int(req.query.page_size, 'page_size', { def: 20, min: 1, max: 100 });

  const rows = await db.query(Q.Q1_ORGANIZATIONS,
    [role, status, zipCode, search, pageSize, (page - 1) * pageSize]);
  const total = rows.length ? rows[0].total_count : 0;
  res.json({
    data: rows.map(({ total_count, ...r }) => r),
    meta: { page, page_size: pageSize, total, total_pages: Math.ceil(total / pageSize) },
  });
}));

// GET /organizations/:id  (auxiliary) - one organization
router.get('/:id', wrap(async (req, res) => {
  const id = int(req.params.id, 'id', { required: true, min: 1 });
  const [org] = await db.query(Q.ORGANIZATION_BY_ID, [id]);
  if (!org) throw notFound(`Organization ${id} not found`);
  res.json({ data: org });
}));

// GET /organizations/:id/donation-summary  (Q3) - donor profile by category
router.get('/:id/donation-summary', wrap(async (req, res) => {
  const id = int(req.params.id, 'id', { required: true, min: 1 });
  const [org] = await db.query(Q.ORGANIZATION_BY_ID, [id]);
  if (!org) throw notFound(`Organization ${id} not found`);
  const rows = await db.query(Q.Q3_DONOR_SUMMARY, [id]);
  res.json({
    data: rows,
    meta: {
      organization_id: id,
      organization_name: org.organization_name,
      total_donations: rows.reduce((s, r) => s + r.donations, 0),
      total_servings_donated: rows.reduce((s, r) => s + r.servings_donated, 0),
    },
  });
}));

module.exports = router;

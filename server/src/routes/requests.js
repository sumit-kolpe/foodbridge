// Recipient Requests page: post a request, track its allocations.
const router = require('express').Router();
const db = require('../db');
const Q = require('../queries');
const config = require('../config');
const { wrap, int, timestamp, bad, notFound, conflict } = require('../http');

// POST /requests  (auxiliary) - a recipient posts a food need
router.post('/', wrap(async (req, res) => {
  const b = req.body || {};
  const recipientId = int(b.recipient_org_id, 'recipient_org_id', { required: true, min: 1 });
  const categoryId = int(b.category_id, 'category_id', { required: true, min: 1 });
  const quantity = int(b.requested_quantity, 'requested_quantity', { required: true, min: 1, max: 100000 });
  const neededBy = timestamp(b.needed_by, 'needed_by', { required: true });
  const now = config.now();
  if (neededBy < now) throw bad("'needed_by' must not be in the past");

  const [org] = await db.query(Q.ORGANIZATION_BY_ID, [recipientId]);
  if (!org) throw notFound(`Organization ${recipientId} not found`);
  if (!['recipient', 'both'].includes(org.organization_type)) {
    throw conflict(`Organization ${recipientId} is not registered as a recipient`);
  }
  if (org.status !== 'active') throw conflict(`Organization ${recipientId} is inactive`);
  if (!(await db.query(Q.CATEGORY_EXISTS, [categoryId])).length) {
    throw notFound(`Category ${categoryId} not found`);
  }

  const [request] = await db.query(Q.INSERT_REQUEST, [recipientId, categoryId, quantity, now, neededBy]);
  res.status(201).json({ data: request });
}));

// GET /requests/:id/allocations  (Q4) - who is supplying this request
router.get('/:id/allocations', wrap(async (req, res) => {
  const id = int(req.params.id, 'id', { required: true, min: 1 });
  const [request] = await db.query(Q.REQUEST_BY_ID, [id]);
  if (!request) throw notFound(`Request ${id} not found`);
  const rows = await db.query(Q.Q4_REQUEST_ALLOCATIONS, [id]);
  const active = rows.filter((r) => r.status !== 'cancelled');
  res.json({
    data: rows,
    meta: {
      request,
      servings_allocated: active.reduce((s, r) => s + r.quantity_allocated, 0),
      servings_delivered: rows.filter((r) => r.status === 'delivered')
        .reduce((s, r) => s + r.quantity_allocated, 0),
    },
  });
}));

module.exports = router;

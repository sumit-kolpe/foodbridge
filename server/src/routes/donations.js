// Food Donations page: claimable feed and posting a donation.
const router = require('express').Router();
const db = require('../db');
const Q = require('../queries');
const config = require('../config');
const { wrap, int, timestamp, bad, notFound, conflict } = require('../http');

// GET /donations/available  (Q2) - donations that can still be picked up
router.get('/available', wrap(async (req, res) => {
  const categoryId = int(req.query.category_id, 'category_id', { min: 1 });
  const limit = int(req.query.limit, 'limit', { def: 50, min: 1, max: 200 });
  const now = config.now();
  const rows = await db.query(Q.Q2_AVAILABLE_DONATIONS, [now, categoryId, limit]);
  res.json({ data: rows, meta: { as_of: now, count: rows.length } });
}));

// POST /donations  (auxiliary) - a donor posts surplus food
router.post('/', wrap(async (req, res) => {
  const b = req.body || {};
  const donorId = int(b.donor_org_id, 'donor_org_id', { required: true, min: 1 });
  const categoryId = int(b.category_id, 'category_id', { required: true, min: 1 });
  const quantity = int(b.quantity, 'quantity', { required: true, min: 1, max: 100000 });
  const expiresAt = timestamp(b.expires_at, 'expires_at', { required: true });
  const pickupDeadline = timestamp(b.pickup_deadline, 'pickup_deadline', { required: true });
  const now = config.now();

  if (expiresAt <= now) throw bad("'expires_at' must be in the future");
  if (pickupDeadline < now) throw bad("'pickup_deadline' must not be in the past");
  if (pickupDeadline > expiresAt) throw bad("'pickup_deadline' must not be after 'expires_at'");

  const [org] = await db.query(Q.ORGANIZATION_BY_ID, [donorId]);
  if (!org) throw notFound(`Organization ${donorId} not found`);
  if (!['donor', 'both'].includes(org.organization_type)) {
    throw conflict(`Organization ${donorId} is not registered as a donor`);
  }
  if (org.status !== 'active') throw conflict(`Organization ${donorId} is inactive`);
  if (!(await db.query(Q.CATEGORY_EXISTS, [categoryId])).length) {
    throw notFound(`Category ${categoryId} not found`);
  }

  const [donation] = await db.query(Q.INSERT_DONATION,
    [donorId, categoryId, quantity, now, expiresAt, pickupDeadline]);
  res.status(201).json({ data: donation });
}));

module.exports = router;

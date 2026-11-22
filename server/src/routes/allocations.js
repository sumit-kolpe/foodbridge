// Allocations: match a donation to a request, then track pickup/delivery.
// Both routes run in a transaction with row locks (SELECT ... FOR UPDATE) so two
// concurrent claims can never over-allocate a donation or a request.
const router = require('express').Router();
const db = require('../db');
const Q = require('../queries');
const config = require('../config');
const { wrap, int, oneOf, notFound, conflict } = require('../http');

// POST /allocations  (auxiliary) - allocate servings of a donation to a request
router.post('/', wrap(async (req, res) => {
  const b = req.body || {};
  const donationId = int(b.donation_id, 'donation_id', { required: true, min: 1 });
  const requestId = int(b.request_id, 'request_id', { required: true, min: 1 });
  const quantity = int(b.quantity, 'quantity', { required: true, min: 1 });
  const now = config.now();

  const result = await db.transaction(async (client) => {
    const { rows: [d] } = await client.query(Q.LOCK_DONATION, [donationId]);
    if (!d) throw notFound(`Donation ${donationId} not found`);
    const { rows: [r] } = await client.query(Q.LOCK_REQUEST, [requestId]);
    if (!r) throw notFound(`Request ${requestId} not found`);

    if (!['available', 'partially_allocated'].includes(d.status)) {
      throw conflict(`Donation ${donationId} is ${d.status}`);
    }
    if (d.pickup_deadline.replace('T', ' ') < now) throw conflict(`Donation ${donationId}'s pickup window has closed`);
    if (!['open', 'partially_fulfilled'].includes(r.status)) {
      throw conflict(`Request ${requestId} is ${r.status}`);
    }
    if (r.needed_by.replace('T', ' ') < now) throw conflict(`Request ${requestId} is past its needed-by time`);
    if (d.category_id !== r.category_id) {
      throw conflict('Donation and request are in different food categories',
        { donation_category_id: d.category_id, request_category_id: r.category_id });
    }
    if (quantity > d.remaining || quantity > r.outstanding) {
      throw conflict('Quantity exceeds what is available or still needed',
        { requested: quantity, donation_remaining: d.remaining, request_outstanding: r.outstanding });
    }

    const { rows: [allocation] } = await client.query(Q.INSERT_ALLOCATION,
      [donationId, requestId, quantity, now]);
    const { rows: [ds] } = await client.query(Q.REFRESH_DONATION_STATUS, [donationId, now]);
    const { rows: [rs] } = await client.query(Q.REFRESH_REQUEST_STATUS, [requestId, now]);
    return { allocation, donation_status: ds.status, request_status: rs.status };
  });

  res.status(201).json({
    data: result.allocation,
    meta: { donation_status: result.donation_status, request_status: result.request_status },
  });
}));

// Allowed status transitions
const NEXT = {
  pending: ['confirmed', 'cancelled'],
  confirmed: ['picked_up', 'cancelled'],
  picked_up: ['delivered'],
  delivered: [],
  cancelled: [],
};

// PATCH /allocations/:id/status  (auxiliary) - advance pickup / delivery status
router.patch('/:id/status', wrap(async (req, res) => {
  const id = int(req.params.id, 'id', { required: true, min: 1 });
  const status = oneOf((req.body || {}).status, 'status',
    ['confirmed', 'picked_up', 'delivered', 'cancelled'], { required: true });
  const now = config.now();

  const result = await db.transaction(async (client) => {
    const { rows: [a] } = await client.query(Q.LOCK_ALLOCATION, [id]);
    if (!a) throw notFound(`Allocation ${id} not found`);
    if (!NEXT[a.status].includes(status)) {
      throw conflict(`Cannot change allocation status from '${a.status}' to '${status}'`,
        { allowed: NEXT[a.status] });
    }
    const { rows: [allocation] } = await client.query(Q.UPDATE_ALLOCATION_STATUS, [id, status, now]);
    const { rows: [ds] } = await client.query(Q.REFRESH_DONATION_STATUS, [a.donation_id, now]);
    const { rows: [rs] } = await client.query(Q.REFRESH_REQUEST_STATUS, [a.request_id, now]);
    return { allocation, donation_status: ds.status, request_status: rs.status };
  });

  res.json({
    data: result.allocation,
    meta: { donation_status: result.donation_status, request_status: result.request_status },
  });
}));

module.exports = router;

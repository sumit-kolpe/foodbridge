// Dashboard, categories and Analytics page routes.
const express = require('express');
const db = require('../db');
const Q = require('../queries');
const config = require('../config');
const { wrap, int, month, bad } = require('../http');

const dashboard = express.Router();
const categories = express.Router();
const analytics = express.Router();

// GET /dashboard/kpis  (Q5) - headline numbers
dashboard.get('/kpis', wrap(async (req, res) => {
  const [kpis] = await db.query(Q.Q5_KPIS);
  res.json({ data: kpis, meta: { as_of: config.now() } });
}));

// GET /categories  (auxiliary) - list for dropdowns
categories.get('/', wrap(async (req, res) => {
  res.json({ data: await db.query(Q.CATEGORIES) });
}));

// GET /categories/demand  (Q6) - requests per category over the last N days
categories.get('/demand', wrap(async (req, res) => {
  const days = int(req.query.days, 'days', { def: 30, min: 1, max: 730 });
  const now = config.now();
  const rows = await db.query(Q.Q6_CATEGORY_DEMAND, [now, days]);
  res.json({ data: rows, meta: { as_of: now, days } });
}));

// GET /analytics/monthly-fulfillment  (Q7)
analytics.get('/monthly-fulfillment', wrap(async (req, res) => {
  const categoryId = int(req.query.category_id, 'category_id', { min: 1 });
  const from = month(req.query.from, 'from', { def: '2025-01-01' });
  const to = month(req.query.to, 'to', { def: `${config.now().slice(0, 7)}-01` });
  if (from > to) throw bad("'from' must not be after 'to'");
  const rows = await db.query(Q.Q7_MONTHLY_FULFILLMENT, [categoryId, from, to]);
  res.json({ data: rows, meta: { from: from.slice(0, 7), to: to.slice(0, 7), category_id: categoryId } });
}));

// GET /analytics/donor-leaderboard  (Q8)
analytics.get('/donor-leaderboard', wrap(async (req, res) => {
  const minDonations = int(req.query.min_donations, 'min_donations', { def: 20, min: 1 });
  const limit = int(req.query.limit, 'limit', { def: 25, min: 1, max: 500 });
  const rows = await db.query(Q.Q8_DONOR_LEADERBOARD, [minDonations, limit]);
  res.json({ data: rows, meta: { min_donations: minDonations, limit } });
}));

// GET /analytics/zip-gaps  (Q9)
analytics.get('/zip-gaps', wrap(async (req, res) => {
  const limit = int(req.query.limit, 'limit', { def: 50, min: 1, max: 100 });
  res.json({ data: await db.query(Q.Q9_ZIP_GAPS, [limit]), meta: { limit } });
}));

// GET /analytics/avoidable-loss  (Q10) - long-running before optimization
analytics.get('/avoidable-loss', wrap(async (req, res) => {
  const days = int(req.query.days, 'days', { def: 14, min: 1, max: 90 });
  const limit = int(req.query.limit, 'limit', { def: 25, min: 1, max: 200 });
  const now = config.now();
  const rows = await db.query(Q.Q10_AVOIDABLE_LOSS, [now, days, limit]);
  res.json({ data: rows, meta: { as_of: now, days, limit } });
}));

// GET /analytics/fully-served-recipients  (Q11)
analytics.get('/fully-served-recipients', wrap(async (req, res) => {
  const days = int(req.query.days, 'days', { def: 180, min: 1, max: 730 });
  const now = config.now();
  const rows = await db.query(Q.Q11_FULLY_SERVED, [now, days]);
  res.json({ data: rows, meta: { as_of: now, days, count: rows.length } });
}));

// GET /analytics/unmet-demand  (Q12) - long-running before optimization
analytics.get('/unmet-demand', wrap(async (req, res) => {
  const days = int(req.query.days, 'days', { def: 14, min: 1, max: 90 });
  const now = config.now();
  const rows = await db.query(Q.Q12_UNMET_DEMAND, [now, days]);
  res.json({ data: rows, meta: { as_of: now, days } });
}));

module.exports = { dashboard, categories, analytics };

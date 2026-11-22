// Request validation and error helpers shared by all routes.

class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const bad = (message, details) => new ApiError(400, 'BAD_REQUEST', message, details);
const notFound = (message) => new ApiError(404, 'NOT_FOUND', message);
const conflict = (message, details) => new ApiError(409, 'CONFLICT', message, details);

/** Wrap an async route handler so thrown errors reach the error middleware. */
const wrap = (fn) => (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next);

const isMissing = (v) => v === undefined || v === null || v === '';

/** Integer parameter with optional default and bounds. */
function int(value, name, { required = false, def, min, max } = {}) {
  if (isMissing(value)) {
    if (required) throw bad(`'${name}' is required`);
    return def === undefined ? null : def;
  }
  if (!/^-?\d+$/.test(String(value))) throw bad(`'${name}' must be an integer`);
  const n = Number(value);
  if (min !== undefined && n < min) throw bad(`'${name}' must be >= ${min}`);
  if (max !== undefined && n > max) throw bad(`'${name}' must be <= ${max}`);
  return n;
}

/** String parameter restricted to a set of allowed values. */
function oneOf(value, name, allowed, { required = false, def } = {}) {
  if (isMissing(value)) {
    if (required) throw bad(`'${name}' is required`);
    return def === undefined ? null : def;
  }
  const v = String(value).toLowerCase();
  if (!allowed.includes(v)) throw bad(`'${name}' must be one of: ${allowed.join(', ')}`);
  return v;
}

/** Free-text parameter, trimmed, with a maximum length. */
function text(value, name, { required = false, max = 100 } = {}) {
  if (isMissing(value)) {
    if (required) throw bad(`'${name}' is required`);
    return null;
  }
  const v = String(value).trim();
  if (v.length > max) throw bad(`'${name}' must be at most ${max} characters`);
  return v || null;
}

/** 5-digit ZIP code. */
function zip(value, name = 'zip') {
  if (isMissing(value)) return null;
  if (!/^\d{5}$/.test(String(value))) throw bad(`'${name}' must be a 5-digit ZIP code`);
  return String(value);
}

/** Timestamp 'YYYY-MM-DD HH:MM[:SS]' or ISO 'YYYY-MM-DDTHH:MM[:SS]' -> 'YYYY-MM-DD HH:MM:SS'. */
function timestamp(value, name, { required = false, def } = {}) {
  if (isMissing(value)) {
    if (required) throw bad(`'${name}' is required`);
    return def === undefined ? null : def;
  }
  const m = String(value).match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(:\d{2})?$/);
  if (!m || Number.isNaN(Date.parse(`${m[1]}T${m[2]}${m[3] || ':00'}Z`))) {
    throw bad(`'${name}' must be a timestamp like 2026-11-10 12:00:00`);
  }
  return `${m[1]} ${m[2]}${m[3] || ':00'}`;
}

/** Month 'YYYY-MM' -> first day 'YYYY-MM-01'. */
function month(value, name, { def } = {}) {
  if (isMissing(value)) return def === undefined ? null : def;
  const m = String(value).match(/^(\d{4})-(0[1-9]|1[0-2])$/);
  if (!m) throw bad(`'${name}' must be a month like 2026-01`);
  return `${m[1]}-${m[2]}-01`;
}

module.exports = { ApiError, bad, notFound, conflict, wrap, int, oneOf, text, zip, timestamp, month };

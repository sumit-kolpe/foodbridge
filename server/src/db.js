// PostgreSQL connection pool and query helpers.
const { Pool, types } = require('pg');
const config = require('./config');

// Return BIGINT (COUNT, SUM of int) and NUMERIC as JS numbers instead of strings.
types.setTypeParser(20, (v) => (v === null ? null : parseInt(v, 10)));     // int8
types.setTypeParser(1700, (v) => (v === null ? null : parseFloat(v)));     // numeric
// Keep TIMESTAMP (without time zone) as 'YYYY-MM-DDTHH:MM:SS' text: no timezone shifting.
types.setTypeParser(1114, (v) => (v === null ? null : v.replace(' ', 'T')));

const pool = new Pool(config.db);

/** Run one parameterized statement; returns the rows. */
async function query(text, params = []) {
  const result = await pool.query(text, params);
  return result.rows;
}

/** Run fn(client) inside a transaction: BEGIN ... COMMIT, or ROLLBACK on error. */
async function transaction(fn) {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const value = await fn(client);
    await client.query('COMMIT');
    return value;
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
}

module.exports = { pool, query, transaction };

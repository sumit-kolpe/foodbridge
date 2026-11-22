// Central configuration, read once from environment variables (.env).
require('dotenv').config();

const AS_OF = process.env.AS_OF || '2026-11-10 12:00:00';
const asOfMs = Date.parse(AS_OF.replace(' ', 'T') + 'Z');
if (Number.isNaN(asOfMs)) {
  throw new Error(`Invalid AS_OF value: "${AS_OF}" (expected YYYY-MM-DD HH:MM:SS)`);
}
const startedMs = Date.now();

/** Format a UTC millisecond timestamp as 'YYYY-MM-DD HH:MM:SS' (timezone-free, like the DB). */
function fmt(ms) {
  return new Date(ms).toISOString().slice(0, 19).replace('T', ' ');
}

module.exports = {
  port: Number(process.env.PORT) || 8080,
  db: {
    host: process.env.DB_HOST || 'localhost',
    port: Number(process.env.DB_PORT) || 5432,
    database: process.env.DB_NAME || 'foodbridge',
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    ssl: process.env.DB_SSL === 'false' ? false : { rejectUnauthorized: false },
    max: 10,
    idleTimeoutMillis: 30000,
  },
  asOf: AS_OF,
  /**
   * The application's clock: starts at the dataset snapshot (AS_OF) and
   * advances in real time while the server runs. Used as "now" everywhere.
   */
  now() {
    return fmt(asOfMs + (Date.now() - startedMs));
  },
};

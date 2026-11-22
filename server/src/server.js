// Entry point: start the HTTP server.
const app = require('./app');
const config = require('./config');

app.listen(config.port, () => {
  console.log(`FoodBridge API listening on http://localhost:${config.port}`);
  console.log(`Database: ${config.db.user}@${config.db.host}:${config.db.port}/${config.db.database}`);
  console.log(`App clock starts at the data snapshot: ${config.asOf}`);
});

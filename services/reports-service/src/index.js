import { createApp } from './app.js';
import { migrate } from './db/migrate.js';
import { pool } from './db/pool.js';
import { config } from './config.js';
import { logger } from './lib/logger.js';

async function main() {
  await migrate();

  const app = createApp();
  const server = app.listen(config.port, () => {
    logger.info(`RPD 311 Reports Service online. Accepting incident reports on port ${config.port}.`);
  });

  const shutdown = (signal) => {
    logger.info(`${signal} received. Closing the Records Office for the day.`);
    server.close(() => {
      pool.end().finally(() => process.exit(0));
    });
  };
  process.on('SIGTERM', () => shutdown('SIGTERM'));
  process.on('SIGINT', () => shutdown('SIGINT'));
}

main().catch((err) => {
  logger.error('Reports Service failed to start.', { error: err.message, stack: err.stack });
  process.exit(1);
});

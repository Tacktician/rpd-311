import multer from 'multer';
import { AppError } from '../lib/errors.js';
import { config } from '../config.js';
import { logger } from '../lib/logger.js';

// Terminal error handler. Normalizes everything into the shared RPD 311 error
// shape: { error, message, requestId, details }.
// eslint-disable-next-line no-unused-vars -- Express requires the 4-arg signature
export function errorHandler(err, req, res, _next) {
  let appError = err;

  if (err instanceof multer.MulterError) {
    appError =
      err.code === 'LIMIT_FILE_SIZE'
        ? new AppError(413, 'PAYLOAD_TOO_LARGE', `Attachment exceeds the ${config.attachments.maxSizeBytes / (1024 * 1024)}MB limit.`)
        : new AppError(400, 'VALIDATION_ERROR', `Malformed upload: ${err.message}.`);
  } else if (err?.type === 'entity.parse.failed') {
    appError = new AppError(400, 'VALIDATION_ERROR', 'Request body is not valid JSON.');
  } else if (!(err instanceof AppError)) {
    logger.error('Unhandled exception while processing request.', {
      requestId: req.requestId,
      error: err?.message,
      stack: err?.stack,
    });
    appError = new AppError(
      500,
      'INTERNAL_ERROR',
      'The Records Office encountered an unexpected condition. The incident has been logged.',
    );
  }

  res.status(appError.statusCode).json({
    error: appError.code,
    message: appError.message,
    requestId: req.requestId,
    details: appError.details ?? [],
  });
}

// 404 for unmatched routes.
export function notFound(req, res) {
  res.status(404).json({
    error: 'NOT_FOUND',
    message: `No route matches ${req.method} ${req.path}.`,
    requestId: req.requestId,
    details: [],
  });
}

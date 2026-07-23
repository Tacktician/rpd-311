// Typed application error. The error handler serializes these into the shared
// RPD 311 error shape: { error, message, requestId, details }.

export class AppError extends Error {
  /**
   * @param {number} statusCode  HTTP status
   * @param {string} code        machine-readable error code (e.g. VALIDATION_ERROR)
   * @param {string} message     human-readable, Raccoon City house tone
   * @param {Array<{field: string, message: string}>} [details]
   */
  constructor(statusCode, code, message, details = []) {
    super(message);
    this.name = 'AppError';
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
  }
}

export const badRequest = (message, details) => new AppError(400, 'VALIDATION_ERROR', message, details);
export const unauthorized = (message) => new AppError(401, 'UNAUTHORIZED', message);
export const forbidden = (message) => new AppError(403, 'FORBIDDEN', message);
export const notFound = (message) => new AppError(404, 'NOT_FOUND', message);
export const payloadTooLarge = (message) => new AppError(413, 'PAYLOAD_TOO_LARGE', message);
export const unsupportedMediaType = (message) => new AppError(415, 'UNSUPPORTED_MEDIA_TYPE', message);

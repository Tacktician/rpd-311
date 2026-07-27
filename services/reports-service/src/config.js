// Central configuration, read from the environment. Values are injected via
// Kubernetes (see k8s/base/) in-cluster, or docker-compose.local.yml locally.

const bool = (v, fallback = false) =>
  v === undefined ? fallback : ['1', 'true', 'yes', 'on'].includes(String(v).toLowerCase());

export const config = {
  port: Number(process.env.PORT ?? 3001),
  logLevel: process.env.LOG_LEVEL ?? 'info',

  postgres: {
    host: process.env.POSTGRES_HOST ?? 'localhost',
    port: Number(process.env.POSTGRES_PORT ?? 5432),
    user: process.env.POSTGRES_USER ?? 'rpd311',
    password: process.env.POSTGRES_PASSWORD ?? 'changeme',
    database: process.env.POSTGRES_DB_REPORTS ?? 'reports',
  },

  s3: {
    bucket: process.env.S3_BUCKET_NAME ?? 'rpd311-attachments',
    region: process.env.S3_REGION ?? 'us-east-1',
    // Points at LocalStack (e.g. http://localstack:4566). The AWS SDK requires a
    // region even though LocalStack ignores it.
    endpoint: process.env.S3_ENDPOINT_URL || undefined,
    presignExpirySeconds: 24 * 60 * 60, // 24 hours, per the OpenAPI spec
  },

  serviceToken: process.env.SERVICE_TOKEN ?? '',

  triageServiceUrl: process.env.TRIAGE_SERVICE_URL ?? 'http://triage-service:3002/v1',
  statusServiceUrl: process.env.STATUS_SERVICE_URL ?? 'http://status-service:3003/v1',

  traceparentPropagationEnabled: bool(process.env.TRACEPARENT_PROPAGATION_ENABLED, true),

  // Attachment constraints (mirrors the OpenAPI spec)
  attachments: {
    maxSizeBytes: 10 * 1024 * 1024, // 10MB
    allowedMimeTypes: ['image/jpeg', 'image/png', 'image/webp'],
  },
};

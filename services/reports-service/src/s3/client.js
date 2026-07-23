import { S3Client, HeadBucketCommand, PutObjectCommand, GetObjectCommand } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import { config } from '../config.js';

// forcePathStyle is required for LocalStack (path-style bucket addressing).
// In EKS, S3_ENDPOINT_URL is unset and the SDK uses virtual-hosted-style against
// real S3. Credentials come from the standard AWS_* env vars.
export const s3 = new S3Client({
  region: config.s3.region,
  endpoint: config.s3.endpoint,
  forcePathStyle: Boolean(config.s3.endpoint),
});

export async function putObject({ key, body, contentType }) {
  await s3.send(
    new PutObjectCommand({
      Bucket: config.s3.bucket,
      Key: key,
      Body: body,
      ContentType: contentType,
    }),
  );
}

// Pre-signed GET URL, valid for 24 hours per the OpenAPI spec.
export function presignGet(key) {
  return getSignedUrl(s3, new GetObjectCommand({ Bucket: config.s3.bucket, Key: key }), {
    expiresIn: config.s3.presignExpirySeconds,
  });
}

export async function checkBucket() {
  await s3.send(new HeadBucketCommand({ Bucket: config.s3.bucket }));
}

#!/bin/sh
# Creates the reports-service attachments bucket once LocalStack is ready.
# Runs automatically via LocalStack's init hook (/etc/localstack/init/ready.d).
set -e

awslocal s3 mb "s3://${S3_BUCKET_NAME:-rpd311-attachments}"

echo "RPD 311: attachment bucket provisioned. Evidence intake online."

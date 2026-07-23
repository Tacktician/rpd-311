// Maps database rows to the response shapes defined in openapi.yaml.
//
// Note on redaction: ReportResponse deliberately has no reporter_name /
// reporter_contact / internal_note fields. By always serializing through this
// function, those columns never leak to public callers — redaction is structural,
// not conditional.

export function toReportResponse(row) {
  const location = { lat: Number(row.lat), lng: Number(row.lng) };
  if (row.address) location.address = row.address;

  const response = {
    reportId: row.report_id,
    type: row.type,
    description: row.description,
    location,
    severity: row.severity,
    status: row.status,
    anonymous: row.anonymous,
    attachmentCount: Number(row.attachment_count ?? 0),
    createdAt: new Date(row.created_at).toISOString(),
    updatedAt: new Date(row.updated_at).toISOString(),
  };
  if (row.triage_reference) response.triageReference = row.triage_reference;
  return response;
}

export function toAttachmentResponse(row, url) {
  const response = {
    attachmentId: row.attachment_id,
    reportId: row.report_id,
    filename: row.filename,
    mimeType: row.mime_type,
    sizeBytes: Number(row.size_bytes),
    url,
    uploadedAt: new Date(row.uploaded_at).toISOString(),
  };
  if (row.caption) response.caption = row.caption;
  return response;
}

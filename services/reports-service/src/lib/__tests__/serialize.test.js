import { toReportResponse, toAttachmentResponse } from '../serialize.js';

describe('toReportResponse', () => {
  const row = {
    report_id: 'a3f1c2d4-7e8b-4a9f-b0c1-2d3e4f5a6b7c',
    type: 'NOISE_COMPLAINT',
    description: 'Sustained groaning from apartment 4B.',
    lat: '44.783100', // NUMERIC comes back as a string from pg
    lng: '-93.218500',
    address: '1428 Arklay Street',
    severity: 'MEDIUM',
    status: 'SUBMITTED',
    anonymous: false,
    attachment_count: 2,
    created_at: '2026-07-22T03:14:00.000Z',
    updated_at: '2026-07-22T03:45:00.000Z',
    // sensitive columns present on the row but must NOT surface:
    reporter_name: 'Leon S. Kennedy',
    reporter_contact: 'leon@rpd.raccoon.gov',
    internal_note: 'do not disclose',
    triage_reference: null,
  };

  test('coerces NUMERIC lat/lng to numbers', () => {
    const out = toReportResponse(row);
    expect(out.location.lat).toBeCloseTo(44.7831);
    expect(out.location.lng).toBeCloseTo(-93.2185);
  });

  test('never leaks reporter identity or internal notes', () => {
    const out = toReportResponse(row);
    expect(out).not.toHaveProperty('reporterName');
    expect(out).not.toHaveProperty('reporterContact');
    expect(out).not.toHaveProperty('internalNote');
    expect(JSON.stringify(out)).not.toContain('Kennedy');
  });

  test('omits triageReference when null', () => {
    expect(toReportResponse(row)).not.toHaveProperty('triageReference');
  });

  test('includes triageReference when present', () => {
    const out = toReportResponse({ ...row, triage_reference: 'b1d2e3f4-8a9b-4c0d-e1f2-3a4b5c6d7e8f' });
    expect(out.triageReference).toBe('b1d2e3f4-8a9b-4c0d-e1f2-3a4b5c6d7e8f');
  });
});

describe('toAttachmentResponse', () => {
  test('maps a row and injects the pre-signed url', () => {
    const out = toAttachmentResponse(
      {
        attachment_id: 'c2e3f4a5-9b0c-4d1e-f2a3-4b5c6d7e8f9a',
        report_id: 'a3f1c2d4-7e8b-4a9f-b0c1-2d3e4f5a6b7c',
        filename: 'incident-photo-01.jpg',
        mime_type: 'image/jpeg',
        size_bytes: 1048576,
        caption: 'Subject visible in doorway.',
        uploaded_at: '2026-07-22T03:20:00.000Z',
      },
      'https://signed.example/photo.jpg',
    );
    expect(out.url).toBe('https://signed.example/photo.jpg');
    expect(out.sizeBytes).toBe(1048576);
    expect(out.caption).toBe('Subject visible in doorway.');
  });
});

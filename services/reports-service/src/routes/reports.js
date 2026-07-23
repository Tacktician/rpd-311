import { Router } from 'express';
import { randomUUID } from 'node:crypto';
import multer from 'multer';
import { pool } from '../db/pool.js';
import { putObject, presignGet } from '../s3/client.js';
import { config } from '../config.js';
import { logger } from '../lib/logger.js';
import { notFound, unsupportedMediaType, badRequest } from '../lib/errors.js';
import { parseCreateReport, parseUpdateStatus, parseListQuery } from '../lib/validation.js';
import { toReportResponse, toAttachmentResponse } from '../lib/serialize.js';
import { forwardToTriage } from '../services/triageClient.js';
import { requireServiceToken } from '../middleware/serviceToken.js';

export const reportsRouter = Router();

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: config.attachments.maxSizeBytes },
});

// Selects a report row plus a live attachment count in one shot.
const SELECT_WITH_COUNT = `
  SELECT r.*,
         (SELECT count(*) FROM attachments a WHERE a.report_id = r.report_id)::int AS attachment_count
  FROM reports r`;

async function loadReport(reportId) {
  const { rows } = await pool.query(`${SELECT_WITH_COUNT} WHERE r.report_id = $1`, [reportId]);
  return rows[0] ?? null;
}

// POST /v1/reports — submit a new incident report.
reportsRouter.post('/', async (req, res, next) => {
  try {
    const body = parseCreateReport(req.body);
    const anonymous = body.anonymous ?? false;
    // When anonymous, reporter identity is never stored even if supplied.
    const reporterName = anonymous ? null : body.reporterName ?? null;
    const reporterContact = anonymous ? null : body.reporterContact ?? null;
    const severity = body.severity ?? 'MEDIUM';

    const { rows } = await pool.query(
      `INSERT INTO reports
         (type, description, lat, lng, address, severity, anonymous, reporter_name, reporter_contact)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
       RETURNING *, 0 AS attachment_count`,
      [
        body.type,
        body.description,
        body.location.lat,
        body.location.lng,
        body.location.address ?? null,
        severity,
        anonymous,
        reporterName,
        reporterContact,
      ],
    );
    const report = rows[0];

    // Respond before triage completes — a report is accepted regardless of
    // triage-service availability. Forwarding is fire-and-forget.
    res.status(201).json(toReportResponse(report));

    forwardToTriage(report, req.outboundHeaders).catch((err) => {
      logger.warn(`triage-service unavailable. Report ${report.report_id} queued for retry.`, {
        error: err.message,
      });
    });
  } catch (err) {
    next(err);
  }
});

// GET /v1/reports — paginated list with filters.
reportsRouter.get('/', async (req, res, next) => {
  try {
    const q = parseListQuery(req.query);
    const where = [];
    const params = [];

    if (q.type) where.push(`type = $${params.push(q.type)}`);
    if (q.status) where.push(`status = $${params.push(q.status)}`);
    if (q.severity) where.push(`severity = $${params.push(q.severity)}`);

    if (q.lat !== undefined) {
      const latIdx = params.push(q.lat);
      const lngIdx = params.push(q.lng);
      const radIdx = params.push(q.radius);
      // Haversine great-circle distance in meters (earth radius 6371000 m).
      // GREATEST/LEAST clamp the acos argument to [-1, 1] to avoid NaN from FP drift.
      where.push(`
        6371000 * acos(GREATEST(-1, LEAST(1,
          cos(radians($${latIdx})) * cos(radians(lat)) * cos(radians(lng) - radians($${lngIdx}))
          + sin(radians($${latIdx})) * sin(radians(lat))
        ))) <= $${radIdx}`);
    }

    const whereSql = where.length ? `WHERE ${where.join(' AND ')}` : '';

    const countRes = await pool.query(`SELECT count(*)::int AS total FROM reports ${whereSql}`, params);
    const total = countRes.rows[0].total;

    const limitIdx = params.push(q.limit);
    const offsetIdx = params.push(q.offset);
    const listRes = await pool.query(
      `${SELECT_WITH_COUNT} ${whereSql} ORDER BY r.created_at DESC LIMIT $${limitIdx} OFFSET $${offsetIdx}`,
      params,
    );

    res.json({
      reports: listRes.rows.map(toReportResponse),
      total,
      limit: q.limit,
      offset: q.offset,
    });
  } catch (err) {
    next(err);
  }
});

// GET /v1/reports/:reportId — public single-report lookup.
reportsRouter.get('/:reportId', async (req, res, next) => {
  try {
    const report = await loadReport(req.params.reportId);
    if (!report) throw notFound(`No report on file with id ${req.params.reportId}.`);
    res.json(toReportResponse(report));
  } catch (err) {
    next(err);
  }
});

// PATCH /v1/reports/:reportId/status — internal only (triage/staff callbacks).
reportsRouter.patch('/:reportId/status', requireServiceToken, async (req, res, next) => {
  try {
    const body = parseUpdateStatus(req.body);
    const { rows } = await pool.query(
      `UPDATE reports
         SET status = $1,
             internal_note = COALESCE($2, internal_note),
             resolved_by = COALESCE($3, resolved_by),
             updated_at = NOW()
       WHERE report_id = $4
       RETURNING *,
         (SELECT count(*) FROM attachments a WHERE a.report_id = reports.report_id)::int AS attachment_count`,
      [body.status, body.note ?? null, body.resolvedBy ?? null, req.params.reportId],
    );
    if (rows.length === 0) throw notFound(`No report on file with id ${req.params.reportId}.`);
    res.json(toReportResponse(rows[0]));
  } catch (err) {
    next(err);
  }
});

// POST /v1/reports/:reportId/attachments — multipart upload to S3.
reportsRouter.post('/:reportId/attachments', upload.single('file'), async (req, res, next) => {
  try {
    if (!req.file) throw badRequest("A 'file' part is required in the multipart upload.");
    if (!config.attachments.allowedMimeTypes.includes(req.file.mimetype)) {
      throw unsupportedMediaType(
        `Unsupported media type '${req.file.mimetype}'. Accepted: ${config.attachments.allowedMimeTypes.join(', ')}.`,
      );
    }

    const report = await loadReport(req.params.reportId);
    if (!report) throw notFound(`No report on file with id ${req.params.reportId}.`);

    const attachmentId = randomUUID();
    const s3Key = `${report.report_id}/${attachmentId}-${req.file.originalname}`;

    await putObject({ key: s3Key, body: req.file.buffer, contentType: req.file.mimetype });

    const { rows } = await pool.query(
      `INSERT INTO attachments (attachment_id, report_id, filename, mime_type, size_bytes, s3_key, caption)
       VALUES ($1, $2, $3, $4, $5, $6, $7)
       RETURNING *`,
      [
        attachmentId,
        report.report_id,
        req.file.originalname,
        req.file.mimetype,
        req.file.size,
        s3Key,
        req.body.caption ?? null,
      ],
    );

    const url = await presignGet(s3Key);
    res.status(201).json(toAttachmentResponse(rows[0], url));
  } catch (err) {
    next(err);
  }
});

// GET /v1/reports/:reportId/attachments — list with pre-signed URLs.
reportsRouter.get('/:reportId/attachments', async (req, res, next) => {
  try {
    const report = await loadReport(req.params.reportId);
    if (!report) throw notFound(`No report on file with id ${req.params.reportId}.`);

    const { rows } = await pool.query(
      `SELECT * FROM attachments WHERE report_id = $1 ORDER BY uploaded_at ASC`,
      [report.report_id],
    );

    const attachments = await Promise.all(
      rows.map(async (row) => toAttachmentResponse(row, await presignGet(row.s3_key))),
    );
    res.json({ attachments });
  } catch (err) {
    next(err);
  }
});

import { jest } from '@jest/globals';
import { parseCreateReport, parseUpdateStatus, parseListQuery } from '../validation.js';
import { AppError } from '../errors.js';

describe('parseCreateReport', () => {
  const valid = {
    type: 'ZOMBIE_SIGHTING',
    description: 'Multiple individuals moving erratically on Main Street.',
    location: { lat: 44.7891, lng: -93.2251, address: 'Raccoon City Main Street' },
    severity: 'CRITICAL',
  };

  test('accepts a well-formed report', () => {
    expect(parseCreateReport(valid)).toMatchObject({ type: 'ZOMBIE_SIGHTING' });
  });

  test('rejects an unknown incident type', () => {
    expect(() => parseCreateReport({ ...valid, type: 'GOLEM_SIGHTING' })).toThrow(AppError);
  });

  test('rejects a description below the minimum length', () => {
    expect(() => parseCreateReport({ ...valid, description: 'too short' })).toThrow(AppError);
  });

  test('rejects an out-of-range latitude with a field-level detail', () => {
    try {
      parseCreateReport({ ...valid, location: { lat: 200, lng: 0 } });
      throw new Error('should have thrown');
    } catch (err) {
      expect(err).toBeInstanceOf(AppError);
      expect(err.statusCode).toBe(400);
      expect(err.details.some((d) => d.field === 'location.lat')).toBe(true);
    }
  });

  test('rejects unknown fields (strict)', () => {
    expect(() => parseCreateReport({ ...valid, hax: true })).toThrow(AppError);
  });
});

describe('parseUpdateStatus', () => {
  test('accepts a valid status transition', () => {
    expect(parseUpdateStatus({ status: 'TRIAGED' })).toEqual({ status: 'TRIAGED' });
  });

  test('rejects an invalid status', () => {
    expect(() => parseUpdateStatus({ status: 'ON_FIRE' })).toThrow(AppError);
  });
});

describe('parseListQuery', () => {
  test('applies defaults when no params given', () => {
    expect(parseListQuery({})).toEqual({
      type: undefined,
      status: undefined,
      severity: undefined,
      limit: 20,
      offset: 0,
    });
  });

  test('requires lat and lng together', () => {
    expect(() => parseListQuery({ lat: '44.78' })).toThrow(AppError);
  });

  test('parses a full location filter with default radius', () => {
    const q = parseListQuery({ lat: '44.78', lng: '-93.22' });
    expect(q.lat).toBeCloseTo(44.78);
    expect(q.radius).toBe(1000);
  });

  test('rejects a limit above the max', () => {
    expect(() => parseListQuery({ limit: '500' })).toThrow(AppError);
  });
});

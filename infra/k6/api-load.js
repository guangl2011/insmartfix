// T-PERF-1 (NFR-1): API p95 < 300 ms at 50 rps for 10 min on staging.
//   k6 run -e BASE_URL=https://api.staging.example -e RATE=50 -e DURATION=10m infra/k6/api-load.js
// At M0 only the health probes exist; M1+ adds the authenticated inbox/detail mix (seeded accounts).
import http from 'k6/http';
import { check } from 'k6';

const BASE_URL = (__ENV.BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');
const RATE = Number(__ENV.RATE || 50);
const DURATION = __ENV.DURATION || '10m';

export const options = {
  scenarios: {
    steady: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: Math.max(10, RATE),
      maxVUs: RATE * 4,
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<300'],
    http_req_failed: ['rate<0.005'],
    checks: ['rate>0.995'],
  },
};

export default function () {
  const res = http.get(`${BASE_URL}/v1/readyz`, { tags: { name: 'readyz' } });
  check(res, { 'readyz 200': (r) => r.status === 200 });
}

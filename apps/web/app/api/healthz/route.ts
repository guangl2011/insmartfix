/** Liveness of the Next.js server itself (compose / host health checks). */
export const dynamic = 'force-dynamic';

export function GET() {
  return Response.json({ status: 'ok', server_time: new Date().toISOString() });
}

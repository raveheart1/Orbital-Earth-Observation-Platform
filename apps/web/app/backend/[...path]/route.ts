import { NextResponse, type NextRequest } from "next/server";

/**
 * Same-origin reverse proxy for the platform API.
 *
 * The browser only ever calls /backend/<path>; this handler forwards the
 * request to `${API_BASE_URL}/<path>?<query>` at request time. That keeps the
 * API origin runtime-configurable (Docker/K8s env) and avoids CORS.
 */

export const dynamic = "force-dynamic";

function apiBaseUrl(): string {
  const base = process.env.API_BASE_URL ?? "http://localhost:8000";
  return base.replace(/\/+$/, "");
}

async function proxy(
  request: NextRequest,
  params: Promise<{ path: string[] }>,
): Promise<NextResponse> {
  const { path } = await params;
  const search = request.nextUrl.search;
  const target = `${apiBaseUrl()}/${path.map(encodeURIComponent).join("/")}${search}`;

  const headers = new Headers();
  headers.set("accept", request.headers.get("accept") ?? "application/json");
  const requestId = request.headers.get("x-request-id");
  if (requestId) headers.set("x-request-id", requestId);

  let body: string | undefined;
  if (request.method === "POST") {
    body = await request.text();
    headers.set(
      "content-type",
      request.headers.get("content-type") ?? "application/json",
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    return NextResponse.json(
      {
        type: "about:blank",
        title: "Bad Gateway",
        status: 502,
        detail: "The platform API is unreachable from the web frontend.",
      },
      {
        status: 502,
        headers: { "content-type": "application/problem+json" },
      },
    );
  }

  const responseHeaders = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType) responseHeaders.set("content-type", contentType);
  const upstreamRequestId = upstream.headers.get("x-request-id");
  if (upstreamRequestId) responseHeaders.set("x-request-id", upstreamRequestId);
  responseHeaders.set("cache-control", "no-store");

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  return proxy(request, context.params);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  return proxy(request, context.params);
}

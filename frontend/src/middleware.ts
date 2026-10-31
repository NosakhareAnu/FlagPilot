import { NextResponse, type NextRequest } from "next/server";

/**
 * Fast redirect for signed-out visitors. This only checks that a session cookie EXISTS; it is a UX shortcut, not the
 * security boundary. Every API call is authorised by the backend, and the app shell re-validates the session.
 */
export function middleware(req: NextRequest) {
  if (!req.cookies.get("fp_session")) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = `?next=${encodeURIComponent(req.nextUrl.pathname)}`;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

// Everything except: login, the public demo (+ its server route), API proxy, and static assets.
export const config = {
  matcher: ["/((?!login|demo|demo-api|api|_next|favicon.ico|icon.svg).*)"],
};

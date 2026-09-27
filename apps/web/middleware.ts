import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

function carry(from: NextResponse, to: NextResponse) {
  from.cookies.getAll().forEach((cookie) => {
    to.cookies.set(cookie);
  });
  for (const name of ["cache-control", "expires", "pragma"]) {
    const value = from.headers.get(name);
    if (value) to.headers.set(name, value);
  }
  return to;
}

export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_PUBLISHABLE_KEY;
  const path = request.nextUrl.pathname;

  if (!url || !key) {
    if (path.startsWith("/desk") || path.startsWith("/author")) {
      const login = new URL("/login", request.url);
      if (path.startsWith("/author")) login.searchParams.set("next", "/author");
      return NextResponse.redirect(login);
    }
    return supabaseResponse;
  }

  const supabase = createServerClient(url, key, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet, headers) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
        supabaseResponse = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) => {
          supabaseResponse.cookies.set(name, value, options);
        });
        Object.entries(headers).forEach(([name, value]) => {
          supabaseResponse.headers.set(name, value);
        });
      },
    },
  });

  const { data } = await supabase.auth.getClaims();
  const signedIn = Boolean(data?.claims?.sub);

  if ((path.startsWith("/desk") || path.startsWith("/author")) && !signedIn) {
    const login = new URL("/login", request.url);
    if (path.startsWith("/author")) login.searchParams.set("next", "/author");
    return carry(supabaseResponse, NextResponse.redirect(login));
  }
  if (path === "/signup") {
    return carry(
      supabaseResponse,
      NextResponse.redirect(new URL(signedIn ? "/desk" : "/login", request.url)),
    );
  }
  if (path === "/login" && signedIn) {
    const next = request.nextUrl.searchParams.get("next");
    const dest = next === "/author" ? "/author" : "/desk";
    return carry(supabaseResponse, NextResponse.redirect(new URL(dest, request.url)));
  }
  return supabaseResponse;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
};

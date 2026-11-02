import type { NextRequest } from 'next/server'

export function middleware(request: NextRequest) {
  const currentUser = request.cookies.get('currentUser')?.value

  if (!currentUser && !request.nextUrl.pathname.startsWith('/auth')) {
    return Response.redirect(new URL('/auth', request.url))
  }

  if (currentUser && request.nextUrl.pathname.startsWith('/auth')) {
    return Response.redirect(new URL('/', request.url))
  }
}

export const config = {
  matcher: ['/((?!api|_next/|.*\\.png$).*)'],
}
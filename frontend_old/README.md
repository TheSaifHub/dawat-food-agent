# Dawat frontend

Next.js 16 (App Router, TypeScript, Tailwind CSS 4).

```bash
npm ci          # install exactly what package-lock.json says
npm run dev     # http://localhost:3000
npm run lint
npm run build
```

Environment variables go in `frontend/.env.local` (see `.env.example` once it exists). Only `NEXT_PUBLIC_*` values reach the browser, and they are baked in at **build** time.

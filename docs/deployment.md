# Deployment

Use distinct Supabase staging and production projects and separate environment sets. Never copy production data or service-role keys into staging.

Railway: select `services/api` as root, build its Dockerfile, run `alembic upgrade head` as the pre-deploy command, expose port 8000, and health-check `/health`. Configure the Autoroa API domains selected for each environment plus all server variables from `.env.example`. The production custom API domain should be under `autoroa.com`; do not guess an existing Railway-generated domain.

Configure browser CORS independently for each Railway environment. Values are comma-separated origins, not URLs with paths or trailing slashes. In staging, `CORS_ORIGINS` must contain the actual provisioned staging frontend origin. After the external Vercel project is renamed, set the preview project and team values to its real project slug and team scope:

```dotenv
CORS_ORIGINS=<actual-staging-frontend-origin>
CORS_VERCEL_PREVIEW_PROJECT=<renamed-vercel-project-slug>
CORS_VERCEL_PREVIEW_TEAM=<vercel-team-scope>
```

When configured, this permits generated HTTPS deployment domains only for that project and team scope. It does not permit other `*.vercel.app` sites. Leave both preview values unset in production and use only the stable production frontend origin:

```dotenv
CORS_ORIGINS=https://autoroa.com
CORS_VERCEL_PREVIEW_PROJECT=
CORS_VERCEL_PREVIEW_TEAM=
```

Local development defaults include `localhost` and `127.0.0.1` on the web ports in `.env.example`. CORS permits browser preflights with the `Authorization` and `Content-Type` headers; authentication and admin authorization are still enforced by the API after a preflight succeeds.

Vercel: import `apps/web`, use pnpm, and set `NEXT_PUBLIC_API_URL` to the environment's real Railway API URL ending in `/api/v1`. Configure the environment-specific public Supabase values. Attach the actual provisioned staging domain to staging and `autoroa.com` to production.

Expo EAS: replace/confirm the `nz.co.autoroa.app` bundle identifiers, configure public environment values and the Supabase OAuth redirect `autoroa://`, then run `eas build --profile development|preview|production`. Use `eas submit --profile production` only after owner approval. Configure Apple/Google OAuth providers in Supabase; no client secret belongs in the app.

DNS should use provider-issued CNAME/A records. Enable Sentry by adding its DSN only after a data/privacy review. Roll back applications by prior image/deployment and databases by a tested forward repair migration.

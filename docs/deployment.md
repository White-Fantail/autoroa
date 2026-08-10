# Deployment

Use distinct Supabase staging and production projects and separate environment sets. Never copy production data or service-role keys into staging.

Railway: select `services/api` as root, build its Dockerfile, run `alembic upgrade head` as the pre-deploy command, expose port 8000, and health-check `/health`. Configure `api-staging.carfolio.co.nz` or `api.carfolio.co.nz` plus all server variables from `.env.example`.

Configure browser CORS independently for each Railway environment. Values are comma-separated origins, not URLs with paths or trailing slashes. The staging environment should use:

```dotenv
CORS_ORIGINS=https://carfolio-web-git-staging-nomadonghos-projects.vercel.app,https://staging.carfolio.co.nz
CORS_VERCEL_PREVIEW_PROJECT=carfolio-web
CORS_VERCEL_PREVIEW_TEAM=nomadonghos-projects
```

This permits generated HTTPS deployment domains for the `carfolio-web` project in the `nomadonghos-projects` Vercel scope. It does not permit other `*.vercel.app` sites. Leave both preview values unset in production and use only the stable production frontend origin:

```dotenv
CORS_ORIGINS=https://carfolio.co.nz
CORS_VERCEL_PREVIEW_PROJECT=
CORS_VERCEL_PREVIEW_TEAM=
```

Local development defaults include `localhost` and `127.0.0.1` on the web ports in `.env.example`. CORS permits browser preflights with the `Authorization` and `Content-Type` headers; authentication and admin authorization are still enforced by the API after a preflight succeeds.

Vercel: import `apps/web`, use pnpm, and set `NEXT_PUBLIC_API_URL` to `https://carfolio-api-staging.up.railway.app/api/v1` in staging and `https://api.carfolio.co.nz/api/v1` in production (or the production Railway URL until the custom domain is attached). Configure the environment-specific public Supabase values. Attach `staging.carfolio.co.nz` to the staging project and `carfolio.co.nz` to production.

Expo EAS: replace/confirm bundle identifiers, configure public environment values and Supabase OAuth redirect `carfolio://`, then run `eas build --profile development|preview|production`. Use `eas submit --profile production` only after owner approval. Configure Apple/Google OAuth providers in Supabase; no client secret belongs in the app.

DNS should use provider-issued CNAME/A records. Enable Sentry by adding its DSN only after a data/privacy review. Roll back applications by prior image/deployment and databases by a tested forward repair migration.

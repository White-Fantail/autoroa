# Deployment

Use distinct Supabase staging and production projects and separate environment sets. Never copy production data or service-role keys into staging.

Railway: select `services/api` as root, build its Dockerfile, run `alembic upgrade head` as the pre-deploy command, expose port 8000, and health-check `/health`. Configure `api-staging.carfolio.co.nz` or `api.carfolio.co.nz` plus all server variables from `.env.example`.

Vercel: import `apps/web`, use pnpm, and configure the environment-specific public API/Supabase values. Attach `staging.carfolio.co.nz` to the staging project and `carfolio.co.nz` to production.

Expo EAS: replace/confirm bundle identifiers, configure public environment values and Supabase OAuth redirect `carfolio://`, then run `eas build --profile development|preview|production`. Use `eas submit --profile production` only after owner approval. Configure Apple/Google OAuth providers in Supabase; no client secret belongs in the app.

DNS should use provider-issued CNAME/A records. Enable Sentry by adding its DSN only after a data/privacy review. Roll back applications by prior image/deployment and databases by a tested forward repair migration.

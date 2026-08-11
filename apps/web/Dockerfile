FROM node:20-alpine

RUN corepack enable && corepack prepare pnpm@9.15.4 --activate

WORKDIR /workspace

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json

RUN pnpm install --filter @autoroa/web... --frozen-lockfile

COPY . .

EXPOSE 3000

CMD ["sh", "-c", "pnpm install --filter @autoroa/web... --frozen-lockfile && exec pnpm --filter @autoroa/web dev --hostname 0.0.0.0"]

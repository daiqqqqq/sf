FROM node:20-alpine AS build

WORKDIR /app
COPY package.json tsconfig.json tsconfig.node.json vite.config.ts index.html /app/
COPY src /app/src

RUN npm install --no-fund --no-audit && npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

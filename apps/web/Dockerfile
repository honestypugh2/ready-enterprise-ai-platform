# Demo UI. Dev server only — this image is for the local compose stack, not
# for production hosting, where the built assets belong behind a CDN.
FROM node:24-slim

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

USER node
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

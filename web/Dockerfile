# Web dev server image for docker-compose (make dev). Dependencies come from package-lock.json.
FROM node:24-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# docker-compose passes --host 0.0.0.0 (D31) and publishes the port on 127.0.0.1 only.
CMD ["npm", "run", "dev"]

# The Vite base URL is baked in at build time, so it must be passed as a
# build arg (see docker-compose.yml's frontend.build.args). Point it at
# whatever host:port a browser on the user's machine can reach the API on —
# usually http://localhost:${API_HOST_PORT}, never the internal service name.
FROM node:20-alpine

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

ARG VITE_API_BASE_URL=http://localhost:8081
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

EXPOSE 5173
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173"]

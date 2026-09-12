/// <reference types="vite/client" />

declare module "*.png" {
  const src: string;
  export default src;
}

interface ImportMetaEnv {
  /** Base URL of the Go backend API, e.g. http://localhost:8080 (local `go run`)
   *  or http://localhost:8081 (docker compose, see API_HOST_PORT). */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

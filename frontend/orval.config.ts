import { defineConfig } from "orval";

// Regenerate with `npm run gen:api` after exporting the backend schema
// (backend: `uv run python scripts/export_openapi.py`).
export default defineConfig({
  jobpilot: {
    input: "./openapi.json",
    output: {
      mode: "tags-split",
      target: "src/lib/api/generated/endpoints.ts",
      schemas: "src/lib/api/generated/model",
      client: "react-query",
      httpClient: "fetch",
      clean: true,
      override: {
        mutator: {
          path: "src/lib/api/fetcher.ts",
          name: "customFetch",
        },
        fetch: {
          includeHttpResponseReturnType: false,
        },
        query: {
          signal: true,
        },
      },
    },
  },
});

import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://www.jordanroth.xyz",
  // /photos/ builds to photos/index.html. CloudFront serves it as the home page
  // of portfolio.jordanroth.xyz (see infra/cloudfront-router.js).
  build: { format: "directory" },
});

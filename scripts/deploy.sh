#!/bin/sh
# Uploads dist/ to the site bucket and clears the CloudFront cache.
# Used by .github/workflows/deploy.yml; also works by hand after `npm run build`.
set -eu

BUCKET="${SITE_BUCKET:-jmtr-personal-site}"
DISTRIBUTION="${SITE_DISTRIBUTION:?set SITE_DISTRIBUTION to the CloudFront distribution id}"

# Files under _astro/ have content hashes in their names, so they never change.
aws s3 sync dist/_astro "s3://$BUCKET/_astro" --delete \
  --cache-control "public, max-age=31536000, immutable"

# Everything else (pages, PDFs, andjulia photos) can change at the same URL.
aws s3 sync dist "s3://$BUCKET" --delete --exclude "_astro/*" \
  --cache-control "public, max-age=300"

aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION" --paths "/*" \
  --query Invalidation.Id --output text

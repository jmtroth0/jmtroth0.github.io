# jordanroth.xyz

Personal site: landing page at <https://www.jordanroth.xyz> and photo gallery at
<https://portfolio.jordanroth.xyz>. Built with [Astro](https://astro.build), hosted on
S3 + CloudFront, infrastructure in Pulumi (Python) under `infra/`.

## Layout

```
src/pages/index.astro        landing page
src/pages/photos/index.astro gallery (served as the home page of portfolio.jordanroth.xyz)
src/pages/404.astro          not-found page
src/layouts/Base.astro       shared <head>: icons, GA4
public/                      copied as-is: andjulia/, deathontherocks/, assets/, images/, icons
scripts/fetch-photos.mjs     downloads gallery photos from S3 before each build
scripts/deploy.sh            uploads dist/ to S3 and clears the CloudFront cache
infra/                       Pulumi: Route 53, S3, CloudFront, certificate, deploy role
```

## Photos

The gallery shows every `.jpg`, `.jpeg`, `.png` and `.webp` under `photos/` in the
S3 bucket `jmtr-portfolio-photos`, newest first by EXIF capture date. To change it,
add or delete files there and re-run the Deploy workflow (Actions tab, "Run
workflow"). HEIC isn't supported; convert to JPG first.

## Development

Needs AWS credentials that can read the photos bucket (e.g. `aws login`).

```shell
npm install
npm run dev      # fetches photos, then http://localhost:4321 (gallery at /photos/)
npm run build    # fetches photos, type-checks, builds to dist/
```

## Deploying

Every push to `master` runs `.github/workflows/deploy.yml`: build, upload to S3,
invalidate CloudFront. It signs in to AWS through GitHub's OIDC as the role in the
`AWS_ROLE_ARN` secret (Pulumi output `deploy_role_arn`).

By hand: `npm run build && SITE_DISTRIBUTION=<id> sh scripts/deploy.sh`.

## Infrastructure

```shell
cd infra
pulumi preview
pulumi up
```

State is in `s3://jmtr-pulumi-state`; secrets are encrypted with the KMS key
`alias/pulumi-personal-site`. `pulumi config set live true` moves the domain names
and DNS to the new distribution (see the comment at the top of `infra/__main__.py`).

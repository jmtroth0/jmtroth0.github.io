"""AWS infrastructure for jordanroth.xyz.

- Route 53 zone and records for the domain.
- The site: Astro build in a private S3 bucket, served by CloudFront.
- An IAM role GitHub Actions assumes (OIDC) to build and deploy the site.

Config `live` (default false) controls whether the new distribution has the domain
names and DNS points at it. While false, www stays on GitHub Pages and portfolio on
the old Gatsby distribution, and the new site is only reachable at its
*.cloudfront.net address for testing.
"""

import json
from pathlib import Path

import pulumi
import pulumi_aws as aws

DOMAIN = "jordanroth.xyz"
WWW = f"www.{DOMAIN}"
PORTFOLIO = f"portfolio.{DOMAIN}"
SITE_DOMAINS = [DOMAIN, WWW, PORTFOLIO]
GITHUB_REPO = "jmtroth0/jmtroth0.github.io"
PHOTOS_BUCKET = "jmtr-portfolio-photos"
# Short TTLs so the cutover (and any rollback) takes effect quickly.
TTL = 300

config = pulumi.Config()
live = config.get_bool("live") or False

account_id = aws.get_caller_identity().account_id
# ACM certificates for CloudFront must be in us-east-1.
us_east_1 = aws.Provider("us-east-1", region="us-east-1")


# --- DNS --------------------------------------------------------------------

zone = aws.route53.Zone(
    "zone",
    name=DOMAIN,
    comment="jordanroth.xyz (managed by Pulumi, personal-site/infra)",
    opts=pulumi.ResourceOptions(protect=True),
)


def record(name: str, type_: str, values: list[str], host: str = "") -> aws.route53.Record:
    return aws.route53.Record(
        name,
        zone_id=zone.zone_id,
        name=f"{host}.{DOMAIN}" if host else DOMAIN,
        type=type_,
        ttl=TTL,
        records=values,
    )


# Shared photo folders, served straight from the photos bucket by CloudFront
# distribution E3B6USP7P9IHB2. Not part of the site.
record("photos", "CNAME", ["dl60g3wduyd6q.cloudfront.net"], host="photos")


# --- Site bucket ------------------------------------------------------------

bucket = aws.s3.Bucket("site", bucket="jmtr-personal-site")

aws.s3.BucketPublicAccessBlock(
    "site",
    bucket=bucket.id,
    block_public_acls=True,
    ignore_public_acls=True,
    block_public_policy=True,
    restrict_public_buckets=True,
)
aws.s3.BucketOwnershipControls(
    "site",
    bucket=bucket.id,
    rule={"object_ownership": "BucketOwnerEnforced"},
)


# --- Certificate ------------------------------------------------------------

cert = aws.acm.Certificate(
    "site",
    domain_name=WWW,
    subject_alternative_names=[DOMAIN, PORTFOLIO],
    validation_method="DNS",
    opts=pulumi.ResourceOptions(provider=us_east_1),
)

# One validation record per name. Keyed by the name so the resources are stable.
validation_records = [
    aws.route53.Record(
        f"cert-validation-{name}",
        zone_id=zone.zone_id,
        name=cert.domain_validation_options.apply(
            lambda opts, n=name: next(o for o in opts if o.domain_name == n).resource_record_name
        ),
        type=cert.domain_validation_options.apply(
            lambda opts, n=name: next(o for o in opts if o.domain_name == n).resource_record_type
        ),
        records=[
            cert.domain_validation_options.apply(
                lambda opts, n=name: next(o for o in opts if o.domain_name == n).resource_record_value
            )
        ],
        ttl=TTL,
        allow_overwrite=True,
    )
    for name in SITE_DOMAINS
]

cert_validation = aws.acm.CertificateValidation(
    "site",
    certificate_arn=cert.arn,
    validation_record_fqdns=[r.fqdn for r in validation_records],
    opts=pulumi.ResourceOptions(provider=us_east_1),
)


# --- CloudFront -------------------------------------------------------------

oac = aws.cloudfront.OriginAccessControl(
    "site",
    name="jmtr-personal-site",
    origin_access_control_origin_type="s3",
    signing_behavior="always",
    signing_protocol="sigv4",
)

router = aws.cloudfront.Function(
    "router",
    name="personal-site-router",
    runtime="cloudfront-js-2.0",
    comment="Host redirects, portfolio gallery, folder index pages",
    code=(Path(__file__).parent / "cloudfront-router.js").read_text(),
    publish=True,
)

CACHING_OPTIMIZED = "658327ea-f89d-4fab-a63d-7e88639e58f6"  # AWS managed cache policy

distribution = aws.cloudfront.Distribution(
    "site",
    enabled=True,
    is_ipv6_enabled=True,
    http_version="http2and3",
    comment="jordanroth.xyz personal site",
    price_class="PriceClass_100",
    aliases=SITE_DOMAINS if live else [],
    origins=[
        {
            "origin_id": "site-bucket",
            "domain_name": bucket.bucket_regional_domain_name,
            "origin_access_control_id": oac.id,
        }
    ],
    default_cache_behavior={
        "target_origin_id": "site-bucket",
        "viewer_protocol_policy": "redirect-to-https",
        "allowed_methods": ["GET", "HEAD"],
        "cached_methods": ["GET", "HEAD"],
        "compress": True,
        "cache_policy_id": CACHING_OPTIMIZED,
        "function_associations": [{"event_type": "viewer-request", "function_arn": router.arn}],
    },
    custom_error_responses=[
        {"error_code": 404, "response_code": 404, "response_page_path": "/404.html", "error_caching_min_ttl": 60},
    ],
    restrictions={"geo_restriction": {"restriction_type": "none"}},
    viewer_certificate=(
        {
            "acm_certificate_arn": cert_validation.certificate_arn,
            "ssl_support_method": "sni-only",
            "minimum_protocol_version": "TLSv1.2_2021",
        }
        if live
        else {"cloudfront_default_certificate": True}
    ),
)

# Only this distribution can read the bucket. ListBucket makes missing files 404
# instead of 403.
aws.s3.BucketPolicy(
    "site",
    bucket=bucket.id,
    policy=pulumi.Output.all(bucket.arn, distribution.arn).apply(
        lambda args: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "CloudFrontRead",
                        "Effect": "Allow",
                        "Principal": {"Service": "cloudfront.amazonaws.com"},
                        "Action": ["s3:GetObject", "s3:ListBucket"],
                        "Resource": [args[0], f"{args[0]}/*"],
                        "Condition": {"StringEquals": {"AWS:SourceArn": args[1]}},
                    }
                ],
            }
        )
    ),
)


# --- Site DNS ---------------------------------------------------------------

if live:
    for name, host in [("apex", ""), ("www", "www"), ("portfolio", "portfolio")]:
        for type_ in ["A", "AAAA"]:
            aws.route53.Record(
                f"{name}-{type_.lower()}-site",
                zone_id=zone.zone_id,
                name=f"{host}.{DOMAIN}" if host else DOMAIN,
                type=type_,
                aliases=[
                    {
                        "name": distribution.domain_name,
                        "zone_id": distribution.hosted_zone_id,
                        "evaluate_target_health": False,
                    }
                ],
            )
else:
    # Before cutover: GitHub Pages serves the bare domain (redirecting to www) and
    # www; the old Gatsby distribution E6XNXE0AVQK1B serves portfolio.
    # www uses A/AAAA rather than a CNAME to jmtroth0.github.io: a CNAME makes CAA
    # checks follow it to github.io, whose CAA records don't allow Amazon, so ACM
    # couldn't issue the site certificate.
    github_pages_a = ["185.199.108.153", "185.199.109.153", "185.199.110.153", "185.199.111.153"]
    github_pages_aaaa = ["2606:50c0:8000::153", "2606:50c0:8001::153", "2606:50c0:8002::153", "2606:50c0:8003::153"]
    record("apex-a", "A", github_pages_a)
    record("www-a", "A", github_pages_a, host="www")
    record("www-aaaa", "AAAA", github_pages_aaaa, host="www")
    record("portfolio", "CNAME", ["d17qug2dku104d.cloudfront.net"], host="portfolio")


# --- GitHub Actions deploy role ---------------------------------------------

github_oidc_arn = f"arn:aws:iam::{account_id}:oidc-provider/token.actions.githubusercontent.com"

deploy_role = aws.iam.Role(
    "github-deploy",
    name="personal-site-github-deploy",
    description=f"GitHub Actions deploys of {GITHUB_REPO}",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Federated": github_oidc_arn},
                    "Action": "sts:AssumeRoleWithWebIdentity",
                    "Condition": {
                        "StringEquals": {
                            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                            "token.actions.githubusercontent.com:sub": f"repo:{GITHUB_REPO}:ref:refs/heads/master",
                        }
                    },
                }
            ],
        }
    ),
)

aws.iam.RolePolicy(
    "github-deploy",
    role=deploy_role.id,
    policy=pulumi.Output.all(bucket.arn, distribution.arn).apply(
        lambda args: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "ReadPhotos",
                        "Effect": "Allow",
                        "Action": ["s3:ListBucket", "s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{PHOTOS_BUCKET}", f"arn:aws:s3:::{PHOTOS_BUCKET}/*"],
                    },
                    {
                        "Sid": "WriteSite",
                        "Effect": "Allow",
                        "Action": ["s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                        "Resource": [args[0], f"{args[0]}/*"],
                    },
                    {
                        "Sid": "Invalidate",
                        "Effect": "Allow",
                        "Action": "cloudfront:CreateInvalidation",
                        "Resource": args[1],
                    },
                ],
            }
        )
    ),
)


pulumi.export("zone_id", zone.zone_id)
pulumi.export("name_servers", zone.name_servers)
pulumi.export("bucket", bucket.bucket)
pulumi.export("distribution_id", distribution.id)
pulumi.export("distribution_domain", distribution.domain_name)
pulumi.export("deploy_role_arn", deploy_role.arn)
pulumi.export("live", live)

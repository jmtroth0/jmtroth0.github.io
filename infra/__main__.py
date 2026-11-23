"""DNS for jordanroth.xyz in Route 53.

Step 1 of the move off Namecheap: these records copy what Namecheap's DNS served
on 2026-11-22, so switching the domain's name servers to this zone changes nothing.
The site itself (Astro on S3 + CloudFront) is added later.
"""

import pulumi
import pulumi_aws as aws

DOMAIN = "jordanroth.xyz"
# Short TTLs so the later site cutover (and any rollback) takes effect quickly.
TTL = 300

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


# GitHub Pages serves the bare domain and redirects it to www.
record("apex-a", "A", ["185.199.108.153", "185.199.109.153", "185.199.110.153", "185.199.111.153"])
record("www", "CNAME", ["jmtroth0.github.io"], host="www")

# Photo portfolio (old Gatsby site) on CloudFront distribution E6XNXE0AVQK1B.
record("portfolio", "CNAME", ["d17qug2dku104d.cloudfront.net"], host="portfolio")

# Shared photo folders, served straight from the jmtr-portfolio-photos bucket by
# CloudFront distribution E3B6USP7P9IHB2. The record had gone missing at Namecheap.
record("photos", "CNAME", ["dl60g3wduyd6q.cloudfront.net"], host="photos")

pulumi.export("zone_id", zone.zone_id)
pulumi.export("name_servers", zone.name_servers)

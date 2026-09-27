# SolveNow — Cloudflare Architecture Guide

## Overview

SolveNow uses Cloudflare as its CDN, WAF, and first-line rate limiter. Traffic flows:

```
Browser → Cloudflare Edge → Your VPS Origin
```

Cloudflare terminates HTTPS, applies WAF rules, rate limits, and caches static assets. The origin server receives traffic only from Cloudflare IPs.

---

## DNS Configuration

| Type  | Name         | Content (Origin IP)      | Proxied |
|-------|--------------|--------------------------|---------|
| A     | `@`          | `<your-vps-ip>`          | ✅ Yes  |
| A     | `api`        | `<your-vps-ip>`          | ✅ Yes  |
| CNAME | `www`        | `yourdomain.com`         | ✅ Yes  |

> **WebSocket (`wss://`)**: WebSockets are supported through Cloudflare's proxy when SSL mode is set to **Full (Strict)**.

---

## SSL / TLS

1. Go to **SSL/TLS → Overview**
2. Set mode to **Full (Strict)**
3. Go to **SSL/TLS → Edge Certificates**
   - Enable: **Always Use HTTPS** ✅
   - Enable: **HSTS** with `max-age=31536000; includeSubDomains` ✅
   - Minimum TLS version: **TLS 1.2** ✅

---

## WAF (Web Application Firewall)

1. Go to **Security → WAF → Managed Rules**
2. Enable: **Cloudflare Managed Ruleset** (OWASP Core Rule Set) ✅
3. Enable: **Cloudflare OWASP Core Ruleset** ✅
4. Set sensitivity to **Medium** initially, tune down if false positives appear.

### Custom WAF Rules

Create these rules under **Security → WAF → Custom Rules**:

```
# Block direct access to /metrics endpoint from public internet
(http.request.uri.path eq "/metrics") → Block

# Block requests not from Cloudflare IPs on the origin port (enforce via firewall, not CF)
```

---

## Rate Limiting

Cloudflare Rate Limiting (under **Security → WAF → Rate Limiting Rules**):

| Rule Name              | Expression                              | Limit       | Period | Action  |
|------------------------|-----------------------------------------|-------------|--------|---------|
| Auth brute-force       | `http.request.uri.path contains "/auth/login"` | 10 req | 60s | Block 10min |
| API global             | `http.request.uri.path starts_with "/api/v1"` | 100 req | 60s | Challenge |

> Note: Cloudflare provides the first-line rate limiting at the edge; application-level SlowAPI rate limiting is not currently enabled.`r`n
---

## Caching Rules

Go to **Rules → Cache Rules** and configure:

| Rule                          | Cache Behavior                          |
|-------------------------------|-----------------------------------------|
| `/api/v1/auth/*`              | Bypass cache (sensitive)                |
| `/api/v1/admin/*`             | Bypass cache                            |
| `/api/v1/knowledge/search`    | Cache 60 seconds (read-heavy, public)   |
| `/_next/static/*`             | Cache for 1 year (Next.js immutable assets) |
| `/api/v1/health`              | Cache 30 seconds                        |

---

## Security Headers (via Transform Rules)

Go to **Rules → Transform Rules → Response Header Modification** and add:

| Header                        | Value                                   |
|-------------------------------|-----------------------------------------|
| `Permissions-Policy`          | `geolocation=(), camera=(), microphone=()` |
| `Referrer-Policy`             | `strict-origin-when-cross-origin`       |

> The application already sends `HSTS`, `X-Frame-Options`, `X-Content-Type-Options`, and `CSP` headers.

---

## Origin Protection

Ensure your VPS firewall (UFW / iptables) only accepts port 80/443 traffic from Cloudflare IP ranges:
- https://www.cloudflare.com/ips-v4
- https://www.cloudflare.com/ips-v6

This prevents attackers from bypassing Cloudflare and hitting the origin directly.

```bash
# Example UFW rules (run on the VPS)
for ip in $(curl -s https://www.cloudflare.com/ips-v4); do
    ufw allow from $ip to any port 80 proto tcp
    ufw allow from $ip to any port 443 proto tcp
done
```


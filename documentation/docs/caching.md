# Caching

Every service in this stack sets `Cache-Control` from one middleware,
`shared/middleware.py::CacheControlMiddleware`. There is no cache policy in a
`Caddyfile` and none at the edge, because the edge cannot tell which visitor a
response belongs to. This page states the rule, the values, and the reason the
rule is safe.

## The rule

> A response may be `public`-cacheable only when the path is ungated (the gate
> resolved `action == "none"`) and the upstream chose that header itself.

The middleware decides in this order:

1. **Debug caches nothing.** With `DEPLOYMENT_TYPE=debug` the response is
   replaced with `no-store`, whatever the upstream asked for, so a deliberately
   `public` value never survives into a development deployment. A value that
   already forbids storage (`private`, `no-store`) is kept verbatim rather than
   rewritten.
2. **Production keeps an existing header.** If the response already carries
   `Cache-Control`, it is returned untouched. A route that made a deliberate
   decision about its own content is not overruled by a path-class default.
3. **Production fills a gap.** Only when the response carries none does the
   middleware write the path class's lifespan.

`is_debug` decides *whether anything is cacheable at all*. Caching is a
production behaviour, so every value in the table below applies to production
only, and debug overrides all of them to `no-store`.

## Values

| Class | Paths | Debug | Production |
|-------|-------|-------|------------|
| API | `/api/`, `/customer/api/`, `/staff/api/`, `/developer/api/`, `/webhook/` | `no-store` | `private, no-store` |
| Static | `/static/` | `no-store` | `public, max-age=86400` |
| Health | `/health` | `no-store` | `public, max-age=3600` |
| HTML | anything unmatched | `no-store` | `private, max-age=300` |

The classes are tested in that order, so the API prefix wins over the health
list: `/api/health` is `private, no-store`, not `public, max-age=3600`. The
`"/api/health"` entry in `_MISC_PATHS` therefore never reaches its own branch.
Point a monitor at `/health`.

`_API_MAX_AGE = 0` sits with the other lifespans but does not produce the API
class's value: the prefix branch returns the literal `private, no-store`, because
that is the value the policy actually wants and a bare `max-age=0` is not a
storage ban.

The constants live at the top of `shared/middleware.py` and are deliberately not
environment variables: four integers do not justify new required config, and a
redeploy is the honest way to change them. Tuning one is a one-line edit.

## The safety net

The gate is what makes "keep the upstream header" safe. GateKeeper demotes any
shared-cacheable value on a response it produced or on a proxied response whose
request it decided, so a gated route cannot publish a `public` page through the
gate. On this stack that happens before the response reaches Cloudflare, which is
a shared cache keyed on the URL alone.

The ungated pass-through is left alone. That is what lets a project publish an
asset on an `action == "none"` path and have it cached at the edge instead of
re-fetched on every embed.

This service is not the gate: it cannot know whether a path was gated, so it
keeps an upstream header and does not demote. The gateway does that on the way
out.

## Verifying a change

Read the header from the running service rather than from the source:

```bash
curl -sI http://127.0.0.1:7031/health | grep -i cache-control
```

A health check should show `public, max-age=3600` once the deployment is not in
debug. A response that shows exactly one `Cache-Control` line is correct; two
lines mean something at the edge is adding rather than replacing, which is always
a defect.

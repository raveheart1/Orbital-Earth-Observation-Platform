"""Create the www -> apex redirect rule in Cloudflare, idempotently.

Redirect Rules are not DNS records, so the DNS "Import" button in the dashboard
cannot create one — it only accepts a BIND zone file. They live in the Rulesets
API, in the `http_request_dynamic_redirect` phase. This script puts the rule
there so the configuration is recorded in the repository rather than clicked.

    export CLOUDFLARE_API_TOKEN=...        # never commit this
    uv run python scripts/cloudflare_redirect_rule.py --dry-run
    uv run python scripts/cloudflare_redirect_rule.py

The token needs, scoped to the one zone:
  * Zone -> Zone -> Read             (to resolve the zone name to its id)
  * Zone -> Single Redirect -> Edit

"Single Redirect" is the token permission that governs Redirect Rules. The
ruleset phase they live in is still named `http_request_dynamic_redirect`, so
the two names disagree; that is Cloudflare's naming, not a mistake here. Older
token UIs may instead offer "Dynamic Redirect" or fold this into "Transform
Rules".

Re-running is safe: a rule with the same description is replaced in place
rather than duplicated, and other rules in the phase are preserved.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API = "https://api.cloudflare.com/client/v4"
PHASE = "http_request_dynamic_redirect"

#: Rules are matched on this so re-runs update rather than append.
DESCRIPTION = "www to apex (managed by scripts/cloudflare_redirect_rule.py)"


class CloudflareError(RuntimeError):
    pass


def _call(method: str, path: str, token: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            errors = json.loads(detail).get("errors", [])
            messages = "; ".join(f"{e.get('code')}: {e.get('message')}" for e in errors)
        except json.JSONDecodeError:
            messages = detail[:400]
        hint = ""
        if exc.code in (401, 403):
            hint = (
                "\n\nThe token is missing a permission. It needs Zone:Read plus "
                "Single Redirect:Edit (some token UIs call it 'Dynamic Redirect' "
                "or fold it into 'Transform Rules'), scoped to this zone."
            )
        raise CloudflareError(f"{method} {path} -> HTTP {exc.code}: {messages}{hint}") from exc
    if not payload.get("success", False):
        raise CloudflareError(f"{method} {path} failed: {payload.get('errors')}")
    result: dict[str, Any] = payload
    return result


def zone_id(token: str, zone_name: str) -> str:
    query = urllib.parse.urlencode({"name": zone_name})
    result = _call("GET", f"/zones?{query}", token)["result"]
    if not result:
        raise CloudflareError(
            f"No zone named {zone_name!r} is visible to this token. Check the "
            "zone name and that the token is scoped to include it."
        )
    return str(result[0]["id"])


def build_rule(source_host: str, target_origin: str, status: int) -> dict[str, Any]:
    """A dynamic redirect, so the path survives.

    A *static* redirect to the bare origin would send /analyses/abc to the home
    page and silently drop the deep link.
    """
    return {
        "action": "redirect",
        "action_parameters": {
            "from_value": {
                "status_code": status,
                "target_url": {"expression": f'concat("{target_origin}", http.request.uri.path)'},
                "preserve_query_string": True,
            }
        },
        "expression": f'(http.host eq "{source_host}")',
        "description": DESCRIPTION,
        "enabled": True,
    }


def apply_rule(token: str, zone: str, rule: dict[str, Any]) -> None:
    zid = zone_id(token, zone)
    entrypoint = f"/zones/{zid}/rulesets/phases/{PHASE}/entrypoint"

    try:
        existing = _call("GET", entrypoint, token)["result"].get("rules", []) or []
    except CloudflareError:
        # The phase has no ruleset until the first rule is created.
        existing = []

    kept = [r for r in existing if r.get("description") != DESCRIPTION]
    replaced = len(kept) != len(existing)
    rules = [
        {
            k: v
            for k, v in r.items()
            if k in {"action", "action_parameters", "expression", "description", "enabled"}
        }
        for r in kept
    ]
    rules.append(rule)

    _call("PUT", entrypoint, token, {"rules": rules})
    verb = "Replaced" if replaced else "Created"
    print(f"{verb} the redirect rule. {len(rules)} rule(s) now in the {PHASE} phase.")

    for check in _call("GET", entrypoint, token)["result"].get("rules", []):
        if check.get("description") == DESCRIPTION:
            print(f"  expression : {check['expression']}")
            params = check["action_parameters"]["from_value"]
            print(f"  target     : {params['target_url']['expression']}")
            print(f"  status     : {params['status_code']}")
            print(f"  enabled    : {check.get('enabled')}")
            return
    raise CloudflareError("Rule was accepted but is not present on read-back.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zone", default="oeop.net", help="Zone name (default: oeop.net)")
    parser.add_argument("--source", default="www.oeop.net", help="Hostname to redirect from")
    parser.add_argument("--target", default="https://oeop.net", help="Origin to redirect to")
    parser.add_argument("--status", type=int, default=301, choices=[301, 302, 307, 308])
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the rule and exit without calling the API"
    )
    args = parser.parse_args()

    rule = build_rule(args.source, args.target, args.status)

    if args.dry_run:
        print(f"Would PUT this rule into the {PHASE} phase of zone {args.zone}:\n")
        print(json.dumps(rule, indent=2))
        return

    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "CLOUDFLARE_API_TOKEN is not set.\n\n"
            "Create one at https://dash.cloudflare.com/profile/api-tokens with\n"
            "  Zone -> Zone -> Read\n"
            "  Zone -> Single Redirect -> Edit\n"
            "scoped to the single zone, then:\n"
            "  export CLOUDFLARE_API_TOKEN=...\n\n"
            "Do not commit it, and revoke it once the rule is in place."
        )

    try:
        apply_rule(token, args.zone, rule)
    except CloudflareError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"\nVerify:\n  curl -sI {args.target.replace('https://', 'https://www.')}/analyses?x=1")


if __name__ == "__main__":
    main()

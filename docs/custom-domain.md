# Serving the platform on a custom domain

The platform runs on `oeop.net`, registered through Cloudflare. Azure Container
Apps issues and auto-renews a free managed TLS certificate for it.

Binding a hostname is a handshake with DNS that Terraform cannot complete on
its own: Azure refuses to issue a certificate for a name that does not already
resolve to the app. So the records go in **first**, and only then is the
hostname added to Terraform. Applying in the other order fails the apply.

## Order of operations

1. Publish the DNS records below in Cloudflare.
2. Wait for them to resolve publicly (verify with the commands in step 2).
3. Add the hostname to `web_custom_domains` and deploy.

---

## 1. DNS records

Two records are needed for the apex, and both must be **DNS only** (grey cloud,
not proxied). A proxied record hides the origin behind Cloudflare, and Azure's
certificate validation then fails because it cannot see the app.

| Type | Name | Value | Proxy |
|---|---|---|---|
| `A` | `@` | `48.214.22.245` | DNS only |
| `TXT` | `asuid` | the domain verification ID (below) | n/a |

Read the current verification ID from Terraform rather than copying it from
here — it belongs to the web Container App, so it changes if that app is ever
destroyed and recreated:

```bash
terraform -chdir=infra/environments/dev output -raw custom_domain_verification_id
```

Or from Azure directly:

```bash
az rest --method get --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.App/containerApps/ca-oeop-dev-web?api-version=2024-03-01" \
  --query "properties.customDomainVerificationId" -o tsv
```

The A-record target is the environment's static inbound IP
(`terraform output environment_static_ip`). It is stable for the life of the
managed environment, but it is *not* reserved if the environment is destroyed.

### `www`

`www.oeop.net` redirects to the apex rather than being bound to Azure as a
second hostname — one certificate, one canonical origin, and no second binding
to keep in sync. In Cloudflare:

- `CNAME` `www` → `oeop.net`, **Proxied** (orange cloud). Cloudflare has to
  terminate the request to redirect it, and its Universal SSL certificate
  covers `www` automatically.
- Rules → Redirect Rules → *Create rule*: if hostname equals `www.oeop.net`,
  then dynamic redirect to `concat("https://oeop.net", http.request.uri.path)`,
  status **301**, preserve query string.

## 2. Verify the records resolve

Do not skip this. Adding the hostname to Terraform before DNS is live produces
a failed apply, and a failed apply in the middle of `deploy-dev` leaves the
workloads half-updated.

```bash
dig +short oeop.net A                 # -> 48.214.22.245
dig +short asuid.oeop.net TXT         # -> the verification ID, in quotes
```

Cloudflare's default TTL is fast, but allow a few minutes. Query an
authoritative resolver (`dig @1.1.1.1 ...`) if a stale local cache is in the
way.

## 3. Bind the hostname

Set the default of `web_custom_domains` in
`infra/environments/dev/variables.tf`:

```hcl
default = [
  {
    hostname   = "oeop.net"
    validation = "HTTP"
  },
]
```

`validation` selects how Azure proves you control the name when it issues the
certificate:

- `CNAME` — for a subdomain that CNAMEs to the app. Azure follows the CNAME.
- `HTTP` — for an **apex** domain. An apex cannot be a CNAME, so Azure fetches
  a token over the A record instead. This is the right choice for `oeop.net`.
- `TXT` — validation via a `_dnsauth` TXT record holding the certificate's
  `validation_token`. Avoid it here: the token is only known after the resource
  starts creating, so it cannot be published in the same apply.

Then merge to `main`. The deploy workflow applies it and the hostname goes live.

### Why this takes three steps, not one

Azure enforces an ordering that cannot be expressed as a single Terraform
apply, and getting it wrong fails the apply:

```
RequireCustomHostnameInEnvironment: Creating managed certificate requires
hostname 'oeop.net' added as a custom hostname to a container app or route
in environment 'cae-oeop-dev'
```

1. **Register the hostname**, with TLS disabled
   (`azurerm_container_app_custom_domain`, `certificate_binding_type =
   "Disabled"`). Ownership is checked against the `asuid` TXT record here.
2. **Issue the certificate** against that now-registered hostname
   (`azurerm_container_app_environment_managed_certificate`, `depends_on` the
   binding).
3. **Attach the certificate to the binding.** Terraform cannot do this in the
   same apply that creates both, so the deploy workflow runs `az containerapp
   hostname bind --certificate <id>` afterwards. That step is idempotent.

Because step 3 happens outside Terraform, the binding declares
`ignore_changes = [certificate_binding_type,
container_app_environment_certificate_id]`. Without it, every later apply would
strip the certificate back off and the domain would start serving TLS errors.

## Renewal

Azure renews managed certificates automatically. Nothing to do — provided the
DNS records stay in place and stay unproxied.

## Why the deploy no longer tears the apps down

The apps and jobs are `count = var.deploy_workloads ? 1 : 0`. The deploy
workflow used to run a stage-1 apply with `deploy_workloads=false` on every
push, which destroyed them, and stage 2 recreated them — minutes of downtime
per push, and the custom-domain binding and certificate destroyed and reissued
each time. Azure rate-limits managed certificate issuance, so that would have
produced intermittent TLS failures on the domain.

Stage 1 now runs only when there is no registry in the Terraform state, which
is the fresh-environment case it was written for. Stage 2 applies the whole
configuration regardless, so foundation changes still land.

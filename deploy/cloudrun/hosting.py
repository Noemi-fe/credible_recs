"""Firebase Hosting in front of the site (2 Nov 2026, Noemi bought crediblepicks.com at Porkbun): Hosting holds the
domain and credible-picks.web.app and hands every request to the Cloud Run service deploy.sh deploys, so the site
has a name people can remember without Cloud Run's preview-only domain mapping or a paid load balancer.

    python -m deploy.cloudrun.hosting release    passes every request on the site's Hosting addresses to the service
    python -m deploy.cloudrun.hosting domains    adds crediblepicks.com, and www sent on to it, where missing
    python -m deploy.cloudrun.hosting status     each domain's state and the DNS records it still needs

Through Firebase Hosting's REST API with gcloud's sign-in, as Noemi's personal site is published (no Firebase CLI or
Node). The DNS records themselves are Noemi's, at Porkbun. What Hosting changes for the site (DEPLOY.md, Firebase
Hosting and the domain): a request may take 60 s at most; the Host header still names the service, the page's Origin
the address the visitor opened (so deploy.sh's SITE_DOMAINS are allowed hosts too); and the visitor's address comes
before one of Google's own (engine.web.client_address).
"""
import json
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

import certifi

PROJECT = "credible-picks"
SITE = "credible-picks"  # the project's default Hosting site: credible-picks.web.app
SERVICE = "credible-recs"  # deploy.sh's SERVICE and REGION
REGION = "europe-west1"
DOMAINS = {"crediblepicks.com": None, "www.crediblepicks.com": "crediblepicks.com"}  # domain: the one it is sent on to
GCLOUD = "/Users/noemi/google-cloud-sdk/bin/gcloud"
API = "https://firebasehosting.googleapis.com/v1beta1"


def config() -> dict:
    """The Hosting version's config: no files of its own, every path handed to the service in its region (Hosting's
    default region would be us-central1)."""
    return {"rewrites": [{"glob": "**", "run": {"serviceId": SERVICE, "region": REGION}}]}


def _token() -> str:
    return subprocess.run([GCLOUD, "auth", "print-access-token"], check=True, capture_output=True,
                          text=True).stdout.strip()


def _call(method: str, url: str, body=None, auth: str = "") -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method)
    request.add_header("Authorization", f"Bearer {auth or _token()}")
    request.add_header("x-goog-user-project", PROJECT)
    request.add_header("Content-Type", "application/json")
    try:
        context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(request, timeout=60, context=context) as response:
            text = response.read().decode()
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as error:
        sys.exit(f"{method} {url} failed: {error.code} {error.read().decode()[:500]}")


def release() -> None:
    auth = _token()
    version = _call("POST", f"{API}/sites/{SITE}/versions", {"config": config()}, auth)["name"]
    _call("POST", f"{API}/{version}:populateFiles", {"files": {}}, auth)
    _call("PATCH", f"{API}/{version}?update_mask=status", {"status": "FINALIZED"}, auth)
    done = _call("POST", f"{API}/sites/{SITE}/releases?versionName={version}", {}, auth)
    print("released", done.get("name"), "to", f"https://{SITE}.web.app")


def _domains(auth: str) -> dict[str, dict]:
    found = _call("GET", f"{API}/projects/{PROJECT}/sites/{SITE}/customDomains", auth=auth)
    return {domain["name"].rsplit("/", 1)[-1]: domain for domain in found.get("customDomains", [])}


def domains() -> None:
    auth = _token()
    there = _domains(auth)
    for name, target in DOMAINS.items():
        if name in there:
            print(name, "is there already")
            continue
        _call("POST", f"{API}/projects/{PROJECT}/sites/{SITE}/customDomains?customDomainId={name}",
              {"redirectTarget": target} if target else {}, auth)
        print("added", name, f"(sent on to {target})" if target else "")


def status() -> None:
    for name, domain in _domains(_token()).items():
        print(f"{name}: host {domain.get('hostState')}, ownership {domain.get('ownershipState')}, "
              f"certificate {domain.get('cert', {}).get('state')}")
        for wanted in domain.get("requiredDnsUpdates", {}).get("desired", []):
            for record in wanted.get("records", []):
                if record.get("requiredAction"):
                    print(f"  {record['requiredAction']} {record['domainName']} {record['type']} {record['rdata']}")
        for discovered in domain.get("requiredDnsUpdates", {}).get("discovered", []):
            for record in discovered.get("records", []):
                if record.get("requiredAction") == "REMOVE":
                    print(f"  REMOVE {record['domainName']} {record['type']} {record['rdata']}")


if __name__ == "__main__":
    commands = {"release": release, "domains": domains, "status": status}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    commands[sys.argv[1]]()

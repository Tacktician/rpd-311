#!/usr/bin/env python3
"""Make rpd311.local resolve inside the cluster by adding it to CoreDNS's hosts block.

The Passport proxy runs in the cluster and has to resolve rpd311.local itself. The name points at
the ingress-nginx controller Service. Safe to run twice. Prints what it did.
Original ConfigMap: kubectl -n kube-system get cm coredns -o yaml  (save it first if you want a backup).
"""
import json
import subprocess
import sys

HOST = "rpd311.local"


def kubectl(*args, stdin=None):
    return subprocess.run(["kubectl", *args], input=stdin, capture_output=True, check=True, text=True).stdout


def main():
    ip = kubectl("-n", "ingress-nginx", "get", "svc", "ingress-nginx-controller", "-o", "jsonpath={.spec.clusterIP}").strip()
    if not ip:
        sys.exit("Could not find the ingress-nginx-controller Service. Is the minikube ingress addon enabled?")
    cm = json.loads(kubectl("-n", "kube-system", "get", "cm", "coredns", "-o", "json"))
    corefile = cm["data"]["Corefile"]
    line = f"       {ip} {HOST}\n"
    if HOST in corefile:
        print(f"CoreDNS already has an entry for {HOST}. Leaving it alone.")
        return
    marker = "    hosts {\n"
    if marker not in corefile:
        sys.exit("This CoreDNS config has no hosts block. Add '%s %s' to it by hand." % (ip, HOST))
    corefile = corefile.replace(marker, marker + line, 1)
    cm["data"]["Corefile"] = corefile
    kubectl("apply", "-f", "-", stdin=json.dumps(cm))
    print(f"Added {ip} {HOST} to the CoreDNS hosts block. CoreDNS reloads it within about 30 seconds.")


if __name__ == "__main__":
    main()

# Bootstraps the Passport lab (PASSPORT.md) so you work in the Passport app and CLI, not in
# kubectl, Helm and Vault. Run it from anywhere:  make -C docs/passport help
#
# Run targets one at a time or use `make up`. Do not use `make -j`: the steps depend on order.
# Every target is safe to run again.

SHELL := /bin/bash
.DEFAULT_GOAL := help
.PHONY: help check up cluster app hosts keys vault vault-secret registry proxy forward public-key \
        status down destroy stretch-up stretch-secret

HERE          := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ROOT          := $(abspath $(HERE)/../..)

# Where keys and generated files live. Must be outside this repository (private keys).
WORKDIR       ?= $(HOME)/passport-lab
PROFILE       ?= minikube
CPUS          ?= 4
# The sample app, Postgres, Redis, LocalStack, the proxy and Vault share one cluster.
# Docker Desktop must have at least this much memory (Settings > Resources).
MEMORY        ?= 7500
CHART_VERSION ?= 0.6.0
REGISTRY      := ociregistry.usepassport.ai
CHART         := oci://$(REGISTRY)/passport/passport

# Dev-mode Vault: fixed root token, in-memory storage. Evaluation only.
VAULT         := kubectl -n passport exec -i deploy/vault -- env VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=lab-root-token vault

# Adds the stretch overlay to the Helm install when `make stretch-up` has created it.
EXTRA_VALUES  := $(if $(wildcard $(WORKDIR)/lab-values-upstream-ca.yaml),-f $(WORKDIR)/lab-values-upstream-ca.yaml)

# Fails with a clear message if a variable is empty. Never prints the value.
define need_var
	@test -n "$${$(1)}" || { echo "Set $(1) first. See the 'Before you start' section of PASSPORT.md."; exit 1; }
endef

help: ## Show this list
	@echo "Passport lab targets (see PASSPORT.md):"; echo
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /|/' | awk -F'|' '{printf "  make %-14s %s\n", $$1, $$2}'
	@echo; echo "Variables you can set: WORKDIR=$(WORKDIR) PROFILE=$(PROFILE) CPUS=$(CPUS) MEMORY=$(MEMORY)"
	@echo "Environment you must export for 'make up': PASSPORT_ORG_ID, PASSPORT_REGISTRY_KEY, POSTMAN_API_KEY"

up: check cluster app keys vault vault-secret registry proxy ## Do everything except the steps in the Passport app
	@echo
	@echo "Done. Next, in this order:"
	@echo "  1. In another terminal:  make -C $(HERE) forward     (leave it running)"
	@echo "  2. Register the proxy in the Passport app. Public key:  make -C $(HERE) public-key"
	@echo "  3. Follow PASSPORT.md from 'Register the proxy' onward."

check: ## Check the tools you need are installed
	@missing=0; for t in docker minikube kubectl helm openssl; do \
	  command -v $$t >/dev/null || { echo "Missing tool: $$t"; missing=1; }; done; \
	  test $$missing -eq 0 || { echo "Install the tools above, then run again."; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "Docker is not running."; exit 1; }
	@echo "Tools found. helm: $$(helm version --short). Helm must be 3.8 or later."

cluster: ## Start minikube with the ingress addon
	minikube start -p $(PROFILE) --cpus $(CPUS) --memory $(MEMORY)
	minikube -p $(PROFILE) addons enable ingress
	minikube -p $(PROFILE) addons enable metrics-server

app: ## Build the three rpd-311 services, load them into minikube and deploy
	@for svc in reports-service triage-service status-service; do \
	  echo "Building $$svc"; \
	  docker build -q -t rpd311/$$svc:1.0.0 $(ROOT)/services/$$svc >/dev/null && \
	  minikube -p $(PROFILE) image load rpd311/$$svc:1.0.0 || exit 1; done
	kubectl apply -f $(ROOT)/k8s/base/namespace.yaml
	kubectl apply -f $(ROOT)/k8s/base/ -f $(ROOT)/k8s/dev/ -f $(ROOT)/k8s/reports-service/ \
	  -f $(ROOT)/k8s/triage-service/ -f $(ROOT)/k8s/status-service/ -f $(ROOT)/k8s/ingress/
	kubectl -n rpd311 wait --for=condition=available deployment --all --timeout=300s
	@echo "A few pod restarts in the first minutes are normal while Postgres and LocalStack start."

hosts: ## Optional: add rpd311.local to /etc/hosts (asks for your password) to call the sample app from your Mac
	@grep -q 'rpd311.local' /etc/hosts && echo "rpd311.local is already in /etc/hosts" || \
	  { echo "127.0.0.1  rpd311.local" | sudo tee -a /etc/hosts >/dev/null && echo "Added. Run 'minikube tunnel -p $(PROFILE)' in another terminal to reach it."; }

keys: ## Create the proxy's CA and reference keys outside this repo, and the passport-keys Secret
	@case "$(WORKDIR)/" in "$(ROOT)/"*) echo "WORKDIR is inside this repository. Private keys must not be. Set WORKDIR elsewhere."; exit 1;; esac
	@mkdir -p $(WORKDIR)/passport-keys
	@cd $(WORKDIR)/passport-keys && if [ -f ca-private-key.pem ] && [ -f reference-private-key.pem ]; then \
	  echo "Keys already exist in $(WORKDIR)/passport-keys. Leaving them alone (a new reference key breaks every reference)."; \
	  else openssl genrsa -out ca-private-key.pem 2048 2>/dev/null && \
	  openssl genrsa -out reference-private-key.pem 2048 2>/dev/null && \
	  openssl rsa -in reference-private-key.pem -pubout -out reference-public-key.pem 2>/dev/null && \
	  chmod 600 *.pem && echo "Generated keys in $(WORKDIR)/passport-keys"; fi
	@kubectl get namespace passport >/dev/null 2>&1 || kubectl create namespace passport
	@kubectl -n passport get secret passport-keys >/dev/null 2>&1 && echo "Secret passport-keys already exists." || \
	  kubectl -n passport create secret generic passport-keys \
	    --from-file=ca-private-key=$(WORKDIR)/passport-keys/ca-private-key.pem \
	    --from-file=reference-private-key=$(WORKDIR)/passport-keys/reference-private-key.pem

vault: ## Run a throwaway dev-mode Vault in the cluster
	kubectl -n passport apply -f $(HERE)/vault-dev.yaml
	kubectl -n passport rollout status deploy/vault --timeout=180s

vault-secret: ## Store $POSTMAN_API_KEY in Vault as postman-api-key. Run again after any minikube restart
	$(call need_var,POSTMAN_API_KEY)
	@printf %s "$$POSTMAN_API_KEY" | $(VAULT) kv put secret/postman-api-key value=- >/dev/null \
	  && echo "Stored postman-api-key ($${#POSTMAN_API_KEY} characters)."
	@$(VAULT) kv get -field=value secret/postman-api-key >/dev/null 2>&1 </dev/null \
	  || { echo "Read-back failed: the value is not in Vault."; exit 1; }

registry: ## Sign in to the Passport registry and create the pull and Vault-token Secrets
	$(call need_var,PASSPORT_REGISTRY_KEY)
	@printf '%s' "$$PASSPORT_REGISTRY_KEY" | docker login $(REGISTRY) --username passport --password-stdin
	@printf '%s' "$$PASSPORT_REGISTRY_KEY" | helm registry login $(REGISTRY) --username passport --password-stdin
	@kubectl -n passport delete secret passport-registry --ignore-not-found >/dev/null
	@kubectl -n passport create secret docker-registry passport-registry \
	  --docker-server=$(REGISTRY) --docker-username=passport --docker-password="$$PASSPORT_REGISTRY_KEY"
	@kubectl -n passport get secret vault-token >/dev/null 2>&1 \
	  || kubectl -n passport create secret generic vault-token --from-literal=token=lab-root-token

proxy: ## Install or update the Passport proxy with Helm
	$(call need_var,PASSPORT_ORG_ID)
	@mkdir -p $(WORKDIR)
	@sed "s/<your-organization-id>/$$PASSPORT_ORG_ID/" $(HERE)/lab-values.yaml > $(WORKDIR)/lab-values.yaml
	helm upgrade --install passport $(CHART) --version $(CHART_VERSION) -n passport \
	  -f $(WORKDIR)/lab-values.yaml $(EXTRA_VALUES)
	kubectl -n passport rollout status deploy/passport-passport --timeout=180s
	@echo "If a port-forward was running, restart it: the pods were replaced."

forward: ## Forward the proxy ports to localhost (leave running; restart after any proxy restart)
	@echo "Forwarding 8081 (management) and 8443 (proxy). Press Ctrl-C to stop."
	kubectl -n passport port-forward deploy/passport-passport 8081:8081 8443:8443

public-key: ## Print the reference public key to paste into the Passport app
	@test -f $(WORKDIR)/passport-keys/reference-public-key.pem || { echo "No key yet. Run: make keys"; exit 1; }
	@cat $(WORKDIR)/passport-keys/reference-public-key.pem

status: ## Show pods, the proxy's readiness and whether Vault still holds the Postman key
	@kubectl get pods -n rpd311; echo; kubectl get pods -n passport; echo
	@curl -s -m 5 --noproxy '*' localhost:8081/readyz || echo "Proxy not reachable on localhost:8081. Run: make forward"; echo
	@if $(VAULT) kv get -field=value secret/postman-api-key >/dev/null 2>&1 </dev/null; then \
	  echo "Vault: postman-api-key is stored."; else echo "Vault: postman-api-key is MISSING. Run: make vault-secret"; fi

down: ## Remove the proxy and Vault (keeps your keys on disk and the sample app)
	-helm uninstall passport -n passport
	-kubectl delete namespace passport
	@echo "Keys are still in $(WORKDIR)/passport-keys. Keep them while the proxy is registered."

destroy: ## Delete the whole minikube cluster. Needs CONFIRM=yes
	@test "$(CONFIRM)" = "yes" || { echo "This deletes the minikube profile '$(PROFILE)'. Run: make destroy CONFIRM=yes"; exit 1; }
	minikube delete -p $(PROFILE)

# ---- Stretch goal: protect the sample app's own SERVICE_TOKEN (see PASSPORT.md) --------------

stretch-up: ## Stretch: HTTPS for rpd311.local, in-cluster DNS, and proxy trust for the certificate
	$(call need_var,PASSPORT_ORG_ID)
	@command -v python3 >/dev/null || { echo "python3 is needed for the CoreDNS step."; exit 1; }
	@mkdir -p $(WORKDIR)
	@[ -f $(WORKDIR)/rpd311-tls.key ] || openssl req -x509 -newkey rsa:2048 -nodes -days 30 \
	  -keyout $(WORKDIR)/rpd311-tls.key -out $(WORKDIR)/rpd311-tls.crt \
	  -subj "/CN=rpd311.local" -addext "subjectAltName=DNS:rpd311.local" 2>/dev/null
	@chmod 600 $(WORKDIR)/rpd311-tls.key
	@kubectl -n rpd311 get secret rpd311-local-tls >/dev/null 2>&1 || kubectl -n rpd311 create secret tls rpd311-local-tls \
	  --cert=$(WORKDIR)/rpd311-tls.crt --key=$(WORKDIR)/rpd311-tls.key
	kubectl apply -f $(HERE)/stretch/ingress-rpd311-tls.yaml
	python3 $(HERE)/stretch/coredns_host.py
	@kubectl -n passport create configmap rpd311-upstream-ca --from-file=rpd311.crt=$(WORKDIR)/rpd311-tls.crt \
	  --dry-run=client -o yaml | kubectl apply -f -
	@cp $(HERE)/stretch/lab-values-upstream-ca.yaml $(WORKDIR)/lab-values-upstream-ca.yaml
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) proxy
	@echo "Restart 'make forward': the proxy pods were replaced."

stretch-secret: ## Stretch: copy SERVICE_TOKEN from the cluster into Vault as service-token (never printed)
	@kubectl -n rpd311 get secret rpd311-secrets -o jsonpath='{.data.SERVICE_TOKEN}' | base64 -d \
	  | $(VAULT) kv put secret/service-token value=- >/dev/null && echo "Stored service-token."

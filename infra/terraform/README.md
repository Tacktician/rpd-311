# infra/terraform — the RPD 311 prod cluster

Terraform for the **EKS prod deployment target**. minikube stays the local testing
environment; this is where a green `main` lands.

The two environments are deliberately near-identical. Both run the same images, the
same manifests under `k8s/`, and the same in-cluster Postgres / Redis / LocalStack from
`k8s/dev/datastores.yaml`. That similarity is what makes the CI gate meaningful: the
`minikube-e2e` job has to pass the full E2E suite on a real cluster before `deploy-prod`
is allowed to touch AWS.

---

## What this provisions

| Resource | Detail |
|---|---|
| VPC | `10.42.0.0/16`, two public subnets across two AZs, internet gateway |
| EKS cluster | `rpd311-prod`, Kubernetes 1.32, public + private API endpoint |
| Managed node group | 2× `t3.medium` on-demand, 30 GiB gp3 each, min 2 / max 4 |
| EKS addons | `vpc-cni`, `kube-proxy`, `coredns`, `metrics-server` |
| ECR | one repository per service (`rpd311/reports-service`, …), immutable tags, keep last 10 |
| IAM | cluster role, node role, EKS access entries for cluster-admin |

**Not provisioned, on purpose:** RDS, ElastiCache, a real S3 bucket, ACM, Route 53, an
ALB, IRSA, and the External Secrets Operator. The datastores run in-cluster and S3 is
LocalStack, exactly as they do on minikube. This is a demo for Postman API Catalog —
the managed-service versions of those components add cost and drift between the two
environments without teaching anything the lessons cover. If you later want them,
`ecr.tf` is the pattern to copy and `k8s/prod/create-secret.sh` is the single place
`POSTGRES_HOST` and `REDIS_URL` need to change.

**No NAT gateway.** Nodes sit in public subnets with public IPs. A NAT gateway is
~$32/month, which is more than half the node group's cost, and the security group rules
still keep nodes unreachable from the internet. Documented in `vpc.tf`.

---

## Cost

Roughly **$0.21/hour, ~$155/month** if you leave it running (us-east-1, on-demand):

| | Hourly | Monthly |
|---|---|---|
| EKS control plane | $0.10 | $73 |
| 2× t3.medium | $0.083 | $61 |
| NLB (ingress-nginx) | $0.023 | $16 |
| 60 GiB gp3 + ECR storage + CloudWatch | — | ~$6 |
| **Total** | **~$0.21** | **~$155** |

Which is why the teardown workflow exists. Destroy after a recording session and the
next merge to `main` rebuilds it.

---

## One-time setup

### 1. Bootstrap (from your laptop, with admin credentials)

`bootstrap/` creates the things that must exist before CI can run terraform: the S3
state bucket, the GitHub Actions OIDC provider, and the IAM role Actions assumes. It
keeps **local** state, because it owns the bucket the main stack's state lives in.

```bash
cd infra/terraform/bootstrap
terraform init
terraform apply \
  -var 'state_bucket_name=rpd311-tfstate-<your-account-id>' \
  -var 'github_repo=Tacktician/rpd-311'
```

S3 bucket names are globally unique across all AWS accounts, hence the account-id
suffix. The `next_steps` output prints the repo configuration to apply.

Nothing in `bootstrap/` costs money and nothing tears it down — the teardown workflow
destroys the main stack only.

### 2. Configure the repo

**Settings → Secrets and variables → Actions**

| Kind | Name | Value |
|---|---|---|
| Variable | `AWS_ROLE_ARN` | the `ci_role_arn` bootstrap output |
| Variable | `AWS_REGION` | `us-east-1` |
| Variable | `TF_STATE_BUCKET` | the `state_bucket` bootstrap output |
| Secret | `SERVICE_TOKEN` | `openssl rand -hex 32` — the `X-Service-Token` shared secret |
| Secret | `POSTMAN_API_KEY` | optional; only the Insights Agent (Lesson 6) reads it |

`deploy-prod` self-skips unless **both** `AWS_ROLE_ARN` and `TF_STATE_BUCKET` are set,
so CI stays green before any of this is configured.

### 3. Create the `production` environment

**Settings → Environments → New environment → `production`**. Both `deploy-prod` and
the teardown job declare it, and the bootstrap role's trust policy names it. Add
required reviewers here if you want a human approval before every prod deploy.

### 4. Optional — kubectl from your laptop

Add your own principal to `admin_principal_arns` (see `terraform.tfvars.example`); the
cluster uses EKS access entries, not the `aws-auth` ConfigMap, so an IAM identity with
no entry cannot reach the API server even with valid credentials.

```bash
aws eks update-kubeconfig --name rpd311-prod --region us-east-1
```

---

## Day-to-day

### Deploying

Merge to `main`. `deploy-prod` runs after `minikube-e2e`, `integration`, and
`docker-build` are green, and then:

1. `terraform apply` — idempotent, so a no-op when the cluster already exists and a
   full rebuild when it does not
2. builds the three images, pushes them to ECR tagged with the commit SHA (skipping any
   tag already in ECR, since repositories are `IMMUTABLE`-tagged)
3. installs ingress-nginx (pinned; provisions the NLB)
4. applies base → secret → datastores → services → `k8s/prod/ingress-prod.yaml`
5. `kubectl set image` to the SHA tag, waits for all three rollouts
6. runs the **same E2E suite** against the deployed cluster
7. writes the public endpoint to the job summary

The public endpoint is the NLB's generated DNS name. `ingress-prod.yaml` has no
`host:` rule, so no domain or ACM certificate is needed:

```bash
curl "http://<nlb-dns-name>/v1/feed"
```

### Tearing down

Run the **Teardown (prod)** workflow (Actions → Teardown (prod) → Run workflow).
`workflow_dispatch` only, and it requires typing `rpd311-prod` to confirm.

- `mode: plan` — prints the destroy plan and stops.
- `mode: destroy` — deletes the ingress-nginx Service first and waits for AWS to
  actually remove the NLB, then runs `terraform destroy`, then sweeps for orphaned
  billable resources.

The NLB ordering matters. Kubernetes creates that load balancer, so terraform has no
record of it; destroying the VPC while it still holds ENIs fails *after* the cluster is
already gone, leaving you paying for a load balancer nothing will clean up.

`terraform destroy` writes the emptied state back to S3, so the next merge to `main`
starts clean rather than trying to adopt resources that no longer exist.

ECR repositories are destroyed too (`force_delete = true`). Images are rebuilt from
source, so nothing is lost — the first deploy after a teardown just has no layer cache
in the registry.

### Cold-start timing

A deploy against an existing cluster takes ~6–8 minutes. A deploy after a teardown
builds a control plane and node group from scratch: **15–20 minutes**, occasionally
more. The job's `timeout-minutes` is 60.

---

## Troubleshooting

**`terraform init` fails on the backend.** The bucket in `TF_STATE_BUCKET` does not
exist or the role cannot read it. Confirm the bootstrap stack applied and the variable
matches its `state_bucket` output.

**`Error: error configuring S3 Backend: no valid credential sources`.** The OIDC trust
policy did not match. It allows `repo:<owner>/<repo>:environment:production` and
`repo:<owner>/<repo>:ref:refs/heads/main` — a job with neither subject cannot assume
the role. Check `github_repo` in the bootstrap stack.

**Deploy succeeds but the NLB address stays empty.** The public subnets need the
`kubernetes.io/role/elb = 1` tag (set in `vpc.tf`) for the cloud controller manager to
consider them. Also give it 2–3 minutes; the job summary says "still provisioning" if
it prints before AWS finishes.

**Pods stuck `Pending`.** Two `t3.medium` nodes are sized for exactly this workload:
three services (5 pods total), three datastores, and the ingress controller. Check
`kubectl -n rpd311 describe pod` for `Insufficient cpu` and raise `node_desired_size`
or `node_instance_types`.

**An image push fails with `ImageTagAlreadyExists`.** Repositories are
`IMMUTABLE`-tagged and the deploy job already guards against re-pushing a SHA it finds
in ECR — this means a *different* image was built for the same commit. Push a new
commit rather than deleting the tag.

**HPA shows `<unknown>` targets.** The `metrics-server` addon did not come up. It is
declared in `eks.tf` and depends on the node group; check
`kubectl -n kube-system get deploy metrics-server`.

**A destroy fails partway.** Re-running the teardown workflow in `destroy` mode is
safe and usually finishes it. If it keeps failing on the VPC, something Kubernetes
created still holds an ENI — look for load balancers in the cluster VPC
(`terraform output vpc_id`).

---

## Local plan without CI

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # edit as needed
terraform init \
  -backend-config="bucket=rpd311-tfstate-<account-id>" \
  -backend-config="region=us-east-1"
terraform plan
```

You need permissions equivalent to the CI role. `terraform fmt -recursive` and
`terraform validate` before committing — the pinned provider lock file carries hashes
for both `linux_amd64` (CI) and `darwin_arm64` (local), so run
`terraform providers lock -platform=linux_amd64 -platform=darwin_arm64` if you bump the
provider version.

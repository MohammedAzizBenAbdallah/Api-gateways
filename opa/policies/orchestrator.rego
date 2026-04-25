package orchestrator

# Canonical policy bundle lives at data.policies (pushed by FastAPI on
# startup and on every admin policy mutation). The bundle has the shape:
#
#   data.policies = {
#     "items":   [ {id, effect, condition: {sensitivity?, tenant?}}, ... ],
#     "version": "<semver>",
#     "hash":    "<sha256-hex>"
#   }
#
# Tests may also pass policies inline via input.policies (a flat array)
# for stateless evaluation.
#
# Expected input shape:
#   input.context: {sensitivity, tenant, service_type}

default allow = true

allow = false {
	count(block) > 0
}

# Resolve the active policy list:
# 1. inline override via input.policies (test path)
# 2. canonical bundle at data.policies.items
# 3. legacy raw array at data.policies (back-compat)
# 4. empty list
policies := input.policies {
	input.policies != null
} else := data.policies.items {
	data.policies != null
	data.policies.items != null
} else := data.policies {
	is_array(data.policies)
} else := []

# Bundle metadata helpers (informational; FastAPI is the source of truth
# for hash/version verification, but we expose them for /v1/data lookups).
bundle_version := data.policies.version {
	data.policies != null
	data.policies.version != null
} else := ""

bundle_hash := data.policies.hash {
	data.policies != null
	data.policies.hash != null
} else := ""

block[pol.id] {
	pol := policies[_]
	policy_matches(pol, input.context)
	should_block(pol, input.context)
}

sensitivity_ok(sn, ctx) {
	sn == null
}

sensitivity_ok(sn, ctx) {
	sn == ctx.sensitivity
}

tenant_ok(tn, ctx) {
	tn == null
}

tenant_ok(tn, ctx) {
	tn == ctx.tenant
}

policy_matches(pol, ctx) {
	sn := object.get(pol.condition, "sensitivity", null)
	tn := object.get(pol.condition, "tenant", null)
	sensitivity_ok(sn, ctx)
	tenant_ok(tn, ctx)
}

should_block(pol, ctx) {
	pol.effect == "deny_all"
}

should_block(pol, ctx) {
	pol.effect == "deny_cloud"
	ctx.service_type == "cloud"
}

should_block(pol, ctx) {
	pol.effect == "allow_onprem_only"
	ctx.service_type != "on-prem"
}

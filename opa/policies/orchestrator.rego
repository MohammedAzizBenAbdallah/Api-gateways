package orchestrator

# Canonical policy set lives at data.policies (pushed by FastAPI on startup
# and on every admin policy mutation). Tests may also pass policies inline
# via input.policies for stateless evaluation.
#
# Expected shapes
# data.policies:  [{id, effect, condition: {sensitivity?, tenant?}}, ...]
# input.policies: same shape (optional override / test path)
# input.context:  {sensitivity, tenant, service_type}

default allow = true

allow = false {
	count(block) > 0
}

policies := input.policies {
	input.policies != null
} else := data.policies {
	data.policies != null
} else := []

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

package orchestrator

# input.policies: [{id, effect, condition: {sensitivity?, tenant?}}, ...]
# input.context: {sensitivity, tenant, service_type}

default allow = true

allow = false {
	count(block) > 0
}

block[pol.id] {
	pol := input.policies[_]
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

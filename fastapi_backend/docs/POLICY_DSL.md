# Governance Policy DSL

This document describes the human-readable YAML format for writing governance policies in the API Gateway.

## Folder structure
The policy file should be located at the root of the backend directory as `policies.yaml`.

## Schema Overview

The policy file consists of a version and a list of policies.

```yaml
version: "1.0.0"
policies:
  - id: "policy-unique-id"
    description: "Brief explanation of the policy"
    condition:
      sensitivity: "HIGH" # Optional: LOW, MEDIUM, HIGH
      tenant: "finance"   # Optional: tenant identifier
    effect: "allow_onprem_only" # Required: allow_onprem_only, deny_cloud, allow_all, deny_all
```

## Condition Block (IF)

The `condition` block defines when a policy applies. All fields in the condition block must match (logical AND).

- **sensitivity**: Matches the sensitivity level of the request (`LOW`, `MEDIUM`, `HIGH`).
- **tenant**: Matches the tenant identified in the request.

## Effect Block (THEN)

The `effect` block defines the action to take when the condition matches.

- **allow_onprem_only**: Restricts the request to on-premises services.
- **deny_cloud**: Explicitly denies routing to cloud services.
- **allow_all**: No restrictions applied by this policy.
- **deny_all**: Immediately denies the request.

## Validation

Policies are validated at startup. If a `policies.yaml` file is invalid (e.g., wrong keys, unknown sensitivity level), the application will fail to start with a descriptive error message.

#!/bin/sh

# Exclude PostHog cookies from SQL injection rule
echo 'SecRuleUpdateTargetById 942290 "!REQUEST_COOKIES:/^ph_/"' \
  >> /etc/modsecurity.d/owasp-crs/rules/REQUEST-999-COMMON-EXCEPTIONS-AFTER.conf

# Exclude Vite dev assets from .js extension restriction (rule 920440)
echo 'SecRule REQUEST_URI "@beginsWith /node_modules/" "id:1001,phase:1,pass,nolog,ctl:ruleRemoveById=920440"' \
  >> /etc/modsecurity.d/owasp-crs/rules/REQUEST-999-COMMON-EXCEPTIONS-AFTER.conf

# Exclude Vite's own source files too (e.g. /src/*.jsx triggers referrer checks)
echo 'SecRule REQUEST_URI "@beginsWith /src/" "id:1002,phase:1,pass,nolog,ctl:ruleRemoveById=920440"' \
  >> /etc/modsecurity.d/owasp-crs/rules/REQUEST-999-COMMON-EXCEPTIONS-AFTER.conf

# Exclude /@vite/ and /@fs/ internal Vite paths
echo 'SecRule REQUEST_URI "@beginsWith /@" "id:1003,phase:1,pass,nolog,ctl:ruleRemoveById=920440"' \
  >> /etc/modsecurity.d/owasp-crs/rules/REQUEST-999-COMMON-EXCEPTIONS-AFTER.conf
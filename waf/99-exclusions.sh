#!/bin/sh
echo 'SecRuleUpdateTargetById 942290 "!REQUEST_COOKIES:/^ph_/"' \
  >> /etc/modsecurity.d/owasp-crs/rules/REQUEST-999-COMMON-EXCEPTIONS-AFTER.conf

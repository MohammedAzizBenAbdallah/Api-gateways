FROM owasp/modsecurity-crs:nginx

# Copy the exclusions script to the entrypoint directory
COPY --chmod=755 99-exclusions.sh /docker-entrypoint.d/99-exclusions.sh

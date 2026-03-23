for i in {1..4}; do
  curl -s -o /dev/null -w "Request $i: %{http_code}\n" \
  --insecure https://localhost:8443/hello
done
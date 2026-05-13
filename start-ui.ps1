Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "🚀 Starting Enterprise AI Gateway UI Links" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Opening background terminals for Port Forwarding..." -ForegroundColor Yellow

# Forward Frontend
Start-Process powershell -WindowStyle Minimized -ArgumentList "-NoExit -Command title 'Frontend (5173)'; kubectl port-forward -n ai-gateway svc/frontend 5173:5173"

# Forward Kong Manager (Admin UI)
Start-Process powershell -WindowStyle Minimized -ArgumentList "-NoExit -Command title 'Kong Manager (8002)'; kubectl port-forward -n ai-gateway svc/kong-cp 8002:8002"
Start-Process powershell -WindowStyle Minimized -ArgumentList "-NoExit -Command title 'Kong Manager (8002)'; kubectl port-forward -n ai-gateway svc/kong-cp 8001:8001"

# Forward Grafana
Start-Process powershell -WindowStyle Minimized -ArgumentList "-NoExit -Command title 'Grafana (3000)'; kubectl port-forward -n ai-monitoring svc/grafana 3000:3000"

Start-Sleep -Seconds 3

Write-Host "✅ All ports forwarded successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "You can now access your project at the following URLs:" -ForegroundColor White
Write-Host "------------------------------------------------------"
Write-Host "🖥️  Frontend UI:    http://localhost:5173" -ForegroundColor Cyan
Write-Host "🔐  Keycloak Login: http://localhost/auth" -ForegroundColor Cyan
Write-Host "🦍  Kong Manager:   http://localhost:8002" -ForegroundColor Cyan
Write-Host "🦍  Kong Manager services:   http://localhost:8001" -ForegroundColor Cyan
Write-Host "📊  Grafana:        http://localhost:3000" -ForegroundColor Cyan
Write-Host ""
Write-Host "Optional admin direct access: kubectl port-forward -n ai-application svc/keycloak 8080:8080" -ForegroundColor Gray
Write-Host "(Note: 3 minimized PowerShell windows were opened to keep the connections alive. Close them when you are done)." -ForegroundColor Gray

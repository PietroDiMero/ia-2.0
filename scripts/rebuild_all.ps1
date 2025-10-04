Write-Host "[rebuild_all] Full stack rebuild (Docker)" -ForegroundColor Cyan
try { docker compose down --remove-orphans } catch {}
docker compose build --no-cache
docker compose up -d
Write-Host "[rebuild_all] Waiting for backend health..." -ForegroundColor Cyan
$ok = $false
for ($i=0; $i -lt 30; $i++) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing http://localhost:8000/health -TimeoutSec 5
    if ($r.StatusCode -eq 200) { Write-Host "[rebuild_all] Backend OK" -ForegroundColor Green; $ok=$true; break }
  } catch {}
  Start-Sleep -Seconds 2
}
if (-not $ok) { Write-Host "[rebuild_all] ERROR: backend not healthy after timeout" -ForegroundColor Red; exit 1 }
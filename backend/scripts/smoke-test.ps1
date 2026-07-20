$ErrorActionPreference = "Stop"

$BaseUrl = if ($env:BASE_URL) { $env:BASE_URL } else { "http://localhost:8080/api/v1" }
$Email = if ($env:EMAIL) { $env:EMAIL } else { "smoke-$(Get-Date -Format 'yyyyMMddHHmmss')@example.com" }
$Password = if ($env:PASSWORD) { $env:PASSWORD } else { "secret123" }
$NewPassword = if ($env:NEW_PASSWORD) { $env:NEW_PASSWORD } else { "newsecret123" }
$Name = if ($env:NAME) { $env:NAME } else { "Smoke Tester" }

Write-Host "==> healthz"
(Invoke-RestMethod "$BaseUrl/healthz" | ConvertTo-Json -Compress)

Write-Host "==> register"
$registerBody = @{ email = $Email; password = $Password; name = $Name } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/register" -ContentType "application/json" -Body $registerBody | ConvertTo-Json -Depth 5

Write-Host "==> login"
$loginBody = @{ email = $Email; password = $Password } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/login" -ContentType "application/json" -Body $loginBody
$login | ConvertTo-Json -Depth 5

$AccessToken = $login.data.access_token
$RefreshToken = $login.data.refresh_token
if (-not $AccessToken -or -not $RefreshToken) {
    throw "Failed to parse tokens from login response"
}

$headers = @{ Authorization = "Bearer $AccessToken" }

Write-Host "==> me"
Invoke-RestMethod -Uri "$BaseUrl/auth/me" -Headers $headers | ConvertTo-Json -Depth 5

Write-Host "==> refresh"
$refreshBody = @{ refresh_token = $RefreshToken } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/refresh" -ContentType "application/json" -Body $refreshBody | ConvertTo-Json -Depth 5

Write-Host "==> change-password"
$changeBody = @{ current_password = $Password; new_password = $NewPassword } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/change-password" -Headers $headers -ContentType "application/json" -Body $changeBody | ConvertTo-Json -Depth 5

Write-Host "==> login with new password"
$login2Body = @{ email = $Email; password = $NewPassword } | ConvertTo-Json
$login2 = Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/login" -ContentType "application/json" -Body $login2Body
$login2 | ConvertTo-Json -Depth 5
$RefreshToken2 = $login2.data.refresh_token

Write-Host "==> logout"
$logoutBody = @{ refresh_token = $RefreshToken2 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/logout" -ContentType "application/json" -Body $logoutBody | ConvertTo-Json -Depth 5

Write-Host "==> wrong password should 401"
try {
    $badBody = @{ email = $Email; password = "wrong-password" } | ConvertTo-Json
    $response = Invoke-WebRequest -Method Post -Uri "$BaseUrl/auth/login" -ContentType "application/json" -Body $badBody -UseBasicParsing
    throw "Expected HTTP 401 but got $($response.StatusCode)"
} catch {
    $httpResponse = $_.Exception.Response
    if ($httpResponse -and [int]$httpResponse.StatusCode -eq 401) {
        Write-Host "HTTP 401"
    } else {
        throw
    }
}

Write-Host "Smoke test complete."

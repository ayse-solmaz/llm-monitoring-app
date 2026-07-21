$ErrorActionPreference = "Stop"

$BaseUrl = if ($env:BASE_URL) { $env:BASE_URL } else { "http://localhost:8080/api/v1" }
$Email = if ($env:EMAIL) { $env:EMAIL } else { "smoke-$(Get-Date -Format 'yyyyMMddHHmmss')@example.com" }
$Password = if ($env:PASSWORD) { $env:PASSWORD } else { "secret123" }
$NewPassword = if ($env:NEW_PASSWORD) { $env:NEW_PASSWORD } else { "newsecret123" }
$Name = if ($env:NAME) { $env:NAME } else { "Smoke Tester" }

function Expect-HttpStatus {
    param(
        [scriptblock]$Request,
        [int]$ExpectedStatus
    )
    try {
        & $Request | Out-Null
        throw "Expected HTTP $ExpectedStatus but request succeeded"
    } catch {
        $httpResponse = $_.Exception.Response
        if ($httpResponse -and [int]$httpResponse.StatusCode -eq $ExpectedStatus) {
            Write-Host "HTTP $ExpectedStatus"
            return
        }
        throw
    }
}

Write-Host "==> healthz"
(Invoke-RestMethod "$BaseUrl/healthz" | ConvertTo-Json -Compress)

Write-Host "==> register invalid email should 400"
Expect-HttpStatus {
    $badRegister = @{ email = "not-an-email"; password = $Password; name = $Name } | ConvertTo-Json
    Invoke-WebRequest -Method Post -Uri "$BaseUrl/auth/register" -ContentType "application/json" -Body $badRegister -UseBasicParsing
} -ExpectedStatus 400

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

Write-Host "==> refresh (token rotation)"
$refreshBody = @{ refresh_token = $RefreshToken } | ConvertTo-Json
$refresh = Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/refresh" -ContentType "application/json" -Body $refreshBody
$refresh | ConvertTo-Json -Depth 5
$RotatedRefreshToken = $refresh.data.refresh_token
if (-not $RotatedRefreshToken) {
    throw "Expected refresh_token in refresh response"
}

Write-Host "==> old refresh token should 401 after rotation"
Expect-HttpStatus {
    $oldRefreshBody = @{ refresh_token = $RefreshToken } | ConvertTo-Json
    Invoke-WebRequest -Method Post -Uri "$BaseUrl/auth/refresh" -ContentType "application/json" -Body $oldRefreshBody -UseBasicParsing
} -ExpectedStatus 401

Write-Host "==> rotated refresh token should work"
$rotatedRefreshBody = @{ refresh_token = $RotatedRefreshToken } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/refresh" -ContentType "application/json" -Body $rotatedRefreshBody | ConvertTo-Json -Depth 5

Write-Host "==> change-password"
$changeBody = @{ current_password = $Password; new_password = $NewPassword } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/change-password" -Headers $headers -ContentType "application/json" -Body $changeBody | ConvertTo-Json -Depth 5

Write-Host "==> refresh with old token should 401 after password change"
Expect-HttpStatus {
    Invoke-WebRequest -Method Post -Uri "$BaseUrl/auth/refresh" -ContentType "application/json" -Body $rotatedRefreshBody -UseBasicParsing
} -ExpectedStatus 401

Write-Host "==> login with new password"
$login2Body = @{ email = $Email; password = $NewPassword } | ConvertTo-Json
$login2 = Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/login" -ContentType "application/json" -Body $login2Body
$login2 | ConvertTo-Json -Depth 5
$RefreshToken2 = $login2.data.refresh_token

Write-Host "==> logout"
$logoutBody = @{ refresh_token = $RefreshToken2 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/logout" -ContentType "application/json" -Body $logoutBody | ConvertTo-Json -Depth 5

Write-Host "==> logout again (idempotent) should 200"
Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/logout" -ContentType "application/json" -Body $logoutBody | ConvertTo-Json -Depth 5

Write-Host "==> wrong password should 401"
Expect-HttpStatus {
    $badBody = @{ email = $Email; password = "wrong-password" } | ConvertTo-Json
    Invoke-WebRequest -Method Post -Uri "$BaseUrl/auth/login" -ContentType "application/json" -Body $badBody -UseBasicParsing
} -ExpectedStatus 401

Write-Host "==> rate limit should 429"
$rateLimitBody = @{ email = "ratelimit@example.com"; password = "wrong-password" } | ConvertTo-Json
$got429 = $false
for ($i = 1; $i -le 20; $i++) {
    try {
        $response = Invoke-WebRequest -Method Post -Uri "$BaseUrl/auth/login" -ContentType "application/json" -Body $rateLimitBody -UseBasicParsing
        if ($response.StatusCode -eq 401) {
            continue
        }
        throw "Expected HTTP 401 or 429 but got $($response.StatusCode)"
    } catch {
        $httpResponse = $_.Exception.Response
        if ($httpResponse -and [int]$httpResponse.StatusCode -eq 429) {
            Write-Host "HTTP 429"
            $got429 = $true
            break
        }
        if ($httpResponse -and [int]$httpResponse.StatusCode -eq 401) {
            continue
        }
        throw
    }
}
if (-not $got429) {
    throw "Expected HTTP 429 but rate limit was not triggered"
}

Write-Host "==> create llm session"
$sessionBody = @{
    model_id = "gemma-2-2b-it-q4f16_1-MLC"
    device_info = "smoke-test"
    model_load_ms = 1200
} | ConvertTo-Json
$session = Invoke-RestMethod -Method Post -Uri "$BaseUrl/llm/sessions" -Headers $headers -ContentType "application/json" -Body $sessionBody
$session | ConvertTo-Json -Depth 5
$SessionId = $session.data.id

Write-Host "==> create llm message"
$messageBody = @{
    role = "assistant"
    content = "Hello from smoke test"
    ttft_ms = 250
    tokens_prompt = 12
    tokens_completion = 8
    tokens_per_sec = 18.5
    total_ms = 900
} | ConvertTo-Json
$message = Invoke-RestMethod -Method Post -Uri "$BaseUrl/llm/sessions/$SessionId/messages" -Headers $headers -ContentType "application/json" -Body $messageBody
$message | ConvertTo-Json -Depth 5
$MessageId = $message.data.id

Write-Host "==> create llm score"
$scoreBody = @{
    message_id = $MessageId
    latency_score = 85
    length_score = 70
    format_score = 90
    composite = 82
    decision = "accept"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$BaseUrl/llm/sessions/$SessionId/scores" -Headers $headers -ContentType "application/json" -Body $scoreBody | ConvertTo-Json -Depth 5

Write-Host "==> get llm session detail"
Invoke-RestMethod -Uri "$BaseUrl/llm/sessions/$SessionId" -Headers $headers | ConvertTo-Json -Depth 6

Write-Host "==> list llm sessions"
Invoke-RestMethod -Uri "$BaseUrl/llm/sessions?page=1&limit=10" -Headers $headers | ConvertTo-Json -Depth 5

Write-Host "==> metrics summary"
Invoke-RestMethod -Uri "$BaseUrl/llm/metrics/summary" -Headers $headers | ConvertTo-Json -Depth 5

Write-Host "==> scores summary"
Invoke-RestMethod -Uri "$BaseUrl/llm/scores/summary" -Headers $headers | ConvertTo-Json -Depth 5

Write-Host "==> delete llm session"
Invoke-RestMethod -Method Delete -Uri "$BaseUrl/llm/sessions/$SessionId" -Headers $headers | ConvertTo-Json -Depth 5

Write-Host "Smoke test complete."

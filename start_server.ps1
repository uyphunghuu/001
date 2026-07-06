# Load từ .env — KHÔNG hardcode API key ở đây
# Copy .env.example thành .env và điền giá trị thực
$env:LLM_API_KEY = $env:LLM_API_KEY  # set từ .env hoặc environment
$env:LLM_BASE_URL = if ($env:LLM_BASE_URL) { $env:LLM_BASE_URL } else { "https://api.groq.com/openai/v1" }
$env:LLM_MODEL    = if ($env:LLM_MODEL)    { $env:LLM_MODEL }    else { "llama-3.3-70b-versatile" }

$log = "D:\Laboratory\001\ai-platform\server.log"
$process = Start-Process -PassThru -NoNewWindow python -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level warning" -RedirectStandardOutput $log -RedirectStandardError $log
Write-Host "Server PID: $($process.Id)"
$process.Id

$env:LIVEKIT_AGENT_HTTP_PORT = "8081"
Write-Host "Starting outbound agent on port $env:LIVEKIT_AGENT_HTTP_PORT"
python agent.py start --port 8081 
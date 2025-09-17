@echo off
set LIVEKIT_AGENT_HTTP_PORT=8081
echo Starting outbound agent on port %LIVEKIT_AGENT_HTTP_PORT%
python agent.py start --port 8081 
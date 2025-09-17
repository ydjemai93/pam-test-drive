@echo off
echo Starting OUTBOUND Agent Worker...
set AGENT_MODE=outbound
rem The port is now passed as a command-line argument to ensure it's used.
echo AGENT_MODE set to %AGENT_MODE%
python agent.py start --port 8081 
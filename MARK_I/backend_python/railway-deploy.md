# 🚂 Railway Deployment Guide for PAM Agent System

## Why Railway for Agents?
- ✅ **Persistent processes** for long-running voice calls
- ✅ **No timeout limits** for 30+ minute conversations
- ✅ **WebSocket support** for real-time audio
- ✅ **Environment variables** management
- ✅ **Auto-scaling** based on usage
- ✅ **Built-in monitoring** and logs

## Deployment Steps

### 1. Environment Variables Setup
```bash
# Core LiveKit Configuration
LIVEKIT_URL=wss://pamtestdrive-euxn3osq.livekit.cloud
LIVEKIT_API_KEY=APIFcVSnRbipq7M
LIVEKIT_API_SECRET=tT1lnn92G4XMLtZ8mG2uE4IdLWA3zpBGBOaVTMl2zyO
LIVEKIT_SIP_FQDN=2j3ruv2tzgf.sip.livekit.cloud

# AI Services
OPENAI_API_KEY=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
DEEPGRAM_API_KEY=67ed6ac5c98ef1067b824d342d5bedbe9ed22314
CARTESIA_API_KEY=sk_car_ZeaLRQkrYNyUztoMUJyWNs

# Telephony
TELNYX_API_KEY=KEY01973BE57C32D9C6C4E4F20334334FE3_9Ec7RRDesnV0IMncbBrENe
TELNYX_CONNECTION_ID=1990082208883122

# Database
SUPABASE_URL=https://ioddvuvaxqywbzfcjmpi.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlvZGR2dXZheHF5d2J6ZmNqbXBpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0ODQ0MDA0MSwiZXhwIjoyMDY0MDE2MDQxfQ.IJQ1XU248fRwft2sqBb0IKI6hqH-eaTqQQw-CxCeEHw

# App Integration
BACKEND_API_URL=https://backendpython-7tm10wuke-ydjemai93s-projects.vercel.app
AGENT_INTERNAL_TOKEN=agent-secure-token-2024-pam
```

### 2. Deploy to Railway
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login to Railway
railway login

# Initialize project
railway init

# Deploy
railway up
```

### 3. Configure Custom Domain (Optional)
- agents.yourdomain.com
- Connect to Railway service

## Configuration Files Already Present:
- ✅ `railway.json` - Railway configuration
- ✅ `Procfile` - Process definition  
- ✅ `requirements.txt` - Python dependencies

## Expected Results:
- 🎙️ **Voice agents** running 24/7
- 📞 **Phone calls** handled with no timeouts
- 🔄 **Auto-scaling** based on call volume
- 📊 **Real-time metrics** and monitoring

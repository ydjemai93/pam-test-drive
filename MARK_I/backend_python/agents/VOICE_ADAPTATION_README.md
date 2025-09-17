# Voice Adaptation - Quick Setup

Enable/disable globally (env)
- VOICE_ADAPTATION_ENABLED=true
- VOICE_ADAPTATION_RATE_LIMIT_S=2.0
- VOICE_ADAPTATION_MEMORY_LIMIT=20

Per-agent overrides (ai_models)
Add a voice_adaptation object to the agent’s ai_models JSON:

```json
{
  "ai_models": {
    "tts": { "provider": "cartesia", "model": "sonic-2-2025-03-07", "voice_id": "..." },
    "llm": { "provider": "openai", "model": "gpt-4o-mini" },
    "stt": { "provider": "deepgram", "model": "nova-3", "language": "fr" },
    "voice_adaptation": {
      "enabled": true,
      "rate_limit_seconds": 1.5,
      "memory_limit": 30
    }
  }
}
```

What it does
- Analyzes sentiment, urgency, complexity, energy
- Adjusts speed/emotions and pre-speech delay per stage
- Mirrors recent sentiment/energy (history influence)

Stages recognized
- greeting, conversation (default), app_action, end_call

Metrics (structured)
- Uses official LiveKit metrics system (STTMetrics, EOUMetrics, LLMMetrics, TTSMetrics)
- Aggregates metrics by speech_id for complete turn analysis
- Emits turn_metrics_complete events with STT final latency, LLM TTFT/total, TTS TTFB/total, and total conversation latency
- See 📊 and 🎯 TURN COMPLETE logs for detailed timing data

Model configuration (ULTRA-OPTIMIZED FOR SPEED)
- STT: Deepgram Nova-3 with French language and ultra-aggressive endpointing (50ms)
- LLM: GPT-4o-mini with ultra-low temperature (0.1) for speed
- TTS: Cartesia sonic-turbo-2025-03-07 for French (optimized for speed)
- Voice adaptation: Minimal delays (10-100ms max, default 20ms)

Local quick test
```bash
python MARK_I/backend_python/agents/voice_adaptation_demo.py
```

Troubleshooting
- Disable: VOICE_ADAPTATION_ENABLED=false
- Fewer updates: raise VOICE_ADAPTATION_RATE_LIMIT_S
- Check logs: look for "VoiceAdapt decision" and "TTS TTFB" lines

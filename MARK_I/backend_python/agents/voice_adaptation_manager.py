from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


logger = logging.getLogger(__name__)


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


@dataclass
class MessageAnalysis:
    """Lightweight message analysis for voice adaptation decisions."""
    sentiment: float  # [-1.0, 1.0] negative to positive
    urgency: float    # [0.0, 1.0]
    complexity: float # [0.0, 1.0]
    energy: float     # [0.0, 1.0]
    contains_question: bool = False
    token_count: int = 0


@dataclass
class VoiceSettings:
    """Provider-agnostic voice settings.

    speed: Relative speaking rate where 1.0 is baseline.
    emotions: Mapping of dimension → intensity in [0.0, 1.0].
    provider_overrides: Optional hints for specific providers (e.g., Cartesia, ElevenLabs).
    """
    speed: float = 1.0
    emotions: Dict[str, float] = field(default_factory=dict)
    allow_interruptions: bool = True
    provider_overrides: Dict[str, Dict] = field(default_factory=dict)


@dataclass
class NaturalTiming:
    """Timing guidance to improve human-like delivery."""
    pre_speech_delay_sec: float = 0.02  # ULTRA-optimized for speed: 20ms default


@dataclass
class AdaptationDecision:
    analysis: MessageAnalysis
    voice_settings: VoiceSettings
    timing: NaturalTiming


class VoiceAdaptationManager:
    """Determines human-like TTS adaptations from lightweight message analysis.

    This manager is provider-agnostic. Use `voice_settings.provider_overrides` hints in a
    tts_node override or wrapper to map settings to specific TTS providers.
    """

    def __init__(
        self,
        *,
        enable_adaptation: bool = True,
        rate_limit_seconds: float = 2.0,
        memory_limit: int = 20,
        history_influence: float = 0.25,
    ) -> None:
        self.enable_adaptation = enable_adaptation
        self.rate_limit_seconds = rate_limit_seconds
        self.memory_limit = memory_limit
        self._last_update_ts: float = 0.0
        self._sentiment_history: List[float] = []
        self._energy_history: List[float] = []
        # Weight of historical mirroring [0,1]; 0 disables mirroring
        self.history_influence = _clamp(history_influence, 0.0, 1.0)

    # ------------------------- Public API ---------------------------------
    def decide(
        self,
        text: str,
        *,
        stage: Optional[str] = None,
        base_language: str = "en",
    ) -> AdaptationDecision:
        """Return adaptation decision for a piece of text.

        stage: Conversation stage hint (e.g., "greeting", "qualifying", "closing").
        base_language: Used for potential provider mapping; not used in heuristics yet.
        """
        if not self.enable_adaptation:
            analysis = self._analyze_message(text)
            return AdaptationDecision(
                analysis=analysis,
                voice_settings=VoiceSettings(),
                timing=NaturalTiming(),
            )

        analysis = self._analyze_message(text)

        # Optionally smooth during rate limit windows
        if self._is_rate_limited():
            analysis.sentiment = self._smoothed(self._sentiment_history, default=analysis.sentiment)
            analysis.energy = self._smoothed(self._energy_history, default=analysis.energy)

        # Record interaction for future mirroring
        self._record_interaction(analysis)
        self._last_update_ts = time.time()

        # Always apply mild historical mirroring for natural continuity
        if self.history_influence > 0.0:
            sm_sent = self._smoothed(self._sentiment_history, default=analysis.sentiment)
            sm_energy = self._smoothed(self._energy_history, default=analysis.energy)
            h = self.history_influence
            analysis.sentiment = (1 - h) * analysis.sentiment + h * sm_sent
            analysis.energy = (1 - h) * analysis.energy + h * sm_energy

        voice_settings = self._determine_voice_settings(analysis, stage)
        timing = self._determine_timing(analysis, stage)
        return AdaptationDecision(analysis=analysis, voice_settings=voice_settings, timing=timing)

    # --------------------- Heuristics and mapping --------------------------
    def _analyze_message(self, text: str) -> MessageAnalysis:
        text_stripped = (text or "").strip()
        tokens = max(1, len(text_stripped.split()))

        lower = text_stripped.lower()
        contains_q = "?" in text_stripped or any(lower.startswith(q) for q in ("who", "what", "when", "where", "why", "how"))

        positive_words = {
            "great", "good", "awesome", "perfect", "thanks", "thank you", "love", "excellent", "amazing",
        }
        negative_words = {
            "bad", "terrible", "awful", "hate", "angry", "upset", "frustrated", "annoyed", "sad",
        }
        urgency_words = {"urgent", "asap", "now", "immediately", "right away", "soon"}

        pos_hits = sum(1 for w in positive_words if w in lower)
        neg_hits = sum(1 for w in negative_words if w in lower)
        urg_hits = sum(1 for w in urgency_words if w in lower)

        # Sentiment in [-1, 1]
        sentiment = 0.0
        if pos_hits or neg_hits:
            sentiment = (pos_hits - neg_hits) / float(pos_hits + neg_hits)
        sentiment = _clamp(sentiment, -1.0, 1.0)

        # Urgency [0,1]
        urgency = _clamp(0.2 * urg_hits, 0.0, 1.0)

        # Complexity [0,1] based on length and punctuation density
        punctuation = sum(ch in ",;:." for ch in text_stripped)
        length_score = _clamp(tokens / 40.0, 0.0, 1.0)  # cap at ~40 words
        punctuation_score = _clamp(punctuation / 10.0, 0.0, 1.0)
        complexity = _clamp(0.6 * length_score + 0.4 * punctuation_score, 0.0, 1.0)

        # Energy [0,1] via exclamations and uppercase ratio
        exclam = text_stripped.count("!")
        uppercase_chars = sum(1 for c in text_stripped if c.isupper())
        letters = sum(1 for c in text_stripped if c.isalpha()) or 1
        caps_ratio = uppercase_chars / letters
        energy = _clamp(0.15 * exclam + 0.8 * caps_ratio + 0.2 * (urgency), 0.0, 1.0)

        return MessageAnalysis(
            sentiment=sentiment,
            urgency=urgency,
            complexity=complexity,
            energy=energy,
            contains_question=contains_q,
            token_count=tokens,
        )

    def _determine_voice_settings(self, analysis: MessageAnalysis, stage: Optional[str]) -> VoiceSettings:
        # Speed: faster for urgency/energy, slower for complexity/negative sentiment
        speed = 1.0
        speed += 0.15 * (analysis.energy - 0.5)
        speed += 0.10 * (analysis.urgency - 0.3)
        speed -= 0.20 * (analysis.complexity)

        # Stage adjustments
        stage_lower = (stage or "").lower()
        if "greeting" in stage_lower:
            speed += 0.05
        elif any(k in stage_lower for k in ("problem", "explain", "clarify")):
            speed -= 0.05

        speed = _clamp(speed, 0.85, 1.15)

        # Emotions: simple interpretable mapping
        emotions = {
            "positivity": _clamp((analysis.sentiment + 1.0) / 2.0, 0.0, 1.0),
            "empathy": _clamp(max(0.0, -analysis.sentiment), 0.0, 1.0),
            "curiosity": 0.55 if analysis.contains_question else 0.35,
            "calmness": _clamp(1.0 - analysis.energy * 0.7, 0.2, 0.95),
        }

        # Provider-specific hints (not all providers support these directly)
        provider_overrides = {
            "cartesia": {
                "speed": round(speed, 3),
                "emotions": emotions,
            },
            "elevenlabs": {
                # ElevenLabs may not expose direct emotion controls in plugin; keep hints
                "stability": _clamp(0.55 + 0.2 * (1.0 - emotions["calmness"]), 0.3, 0.9),
                "style": _clamp(0.5 + 0.2 * emotions["positivity"], 0.3, 0.9),
                "speed": round(speed, 3),
            },
        }

        # Allow interruptions more when user is high-energy/urgent
        allow_interruptions = (analysis.urgency + analysis.energy) >= 0.6

        return VoiceSettings(
            speed=round(speed, 3),
            emotions=emotions,
            allow_interruptions=allow_interruptions,
            provider_overrides=provider_overrides,
        )

    def _determine_timing(self, analysis: MessageAnalysis, stage: Optional[str]) -> NaturalTiming:
        # ULTRA-OPTIMIZED FOR SPEED: Minimal delays for competitive latency
        delay = 0.02  # Base delay reduced to 20ms
        delay += 0.1 * analysis.complexity  # Reduced from 0.3x to 0.1x
        delay += 0.05 * max(0.0, -analysis.sentiment)  # Reduced from 0.1x to 0.05x
        delay -= 0.1 * analysis.urgency  # Reduced from 0.2x to 0.1x

        stage_lower = (stage or "").lower()
        if "greeting" in stage_lower:
            delay -= 0.01  # Minimal greeting delay
        elif any(k in stage_lower for k in ("problem", "explain", "clarify")):
            delay += 0.02  # Reduced from 0.05s to 20ms

        delay = _clamp(delay, 0.01, 0.10)  # Max delay capped at 100ms instead of 250ms
        return NaturalTiming(pre_speech_delay_sec=round(delay, 3))

    # --------------------- Internal helpers --------------------------------
    def _record_interaction(self, analysis: MessageAnalysis) -> None:
        self._sentiment_history.append(analysis.sentiment)
        self._energy_history.append(analysis.energy)
        if len(self._sentiment_history) > self.memory_limit:
            self._sentiment_history.pop(0)
        if len(self._energy_history) > self.memory_limit:
            self._energy_history.pop(0)

    def _is_rate_limited(self) -> bool:
        if self.rate_limit_seconds <= 0:
            return False
        return (time.time() - self._last_update_ts) < self.rate_limit_seconds

    @staticmethod
    def _smoothed(values: List[float], *, default: float, window: int = 5) -> float:
        if not values:
            return default
        recent = values[-window:]
        return sum(recent) / float(len(recent))



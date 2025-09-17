from __future__ import annotations

import os
from voice_adaptation_manager import VoiceAdaptationManager


def run_demo():
    manager = VoiceAdaptationManager(
        enable_adaptation=True,
        rate_limit_seconds=0.0,
        memory_limit=20,
        history_influence=0.25,
    )

    samples = [
        ("greeting", "Hi there! It's great to connect with you today."),
        ("qualifying", "Could you share more about your current setup?"),
        ("problem_solving", "I understand. That sounds frustrating, let's walk through a fix together."),
        ("closing", "Perfect, shall we book Tuesday at 2pm then?"),
        ("closing", "Yes, that works. Thanks a lot!")
    ]

    for stage, text in samples:
        decision = manager.decide(text, stage=stage)
        print(f"\nStage: {stage}")
        print(f"Text: {text}")
        print(f"Delay: {decision.timing.pre_speech_delay_sec}s")
        print(f"Speed: {decision.voice_settings.speed}")
        print(f"Emotions: {decision.voice_settings.emotions}")
        print(f"Interruptions: {decision.voice_settings.allow_interruptions}")


if __name__ == "__main__":
    run_demo()



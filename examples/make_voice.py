"""make_voice.py — free neural narration for ai_smarter_vertical.hmg
Engine : Microsoft Edge-TTS → pip install edge-tts   (free, no API key)
Run    : python make_voice.py                        → writes voice/s1..s5.mp3
Voices : en-US-ChristopherNeural  deep cinematic  (recommended)
         en-US-GuyNeural          energetic
         en-US-AriaNeural         female
         en-GB-RyanNeural         British docu-style
Offline alternative: pip install piper-tts  (fully local, also free)
"""
import asyncio
import os

import edge_tts

VOICE = "en-US-ChristopherNeural"
RATE = "-6%"          # slightly slower = calmer, more cinematic delivery
OUT = "voice"

LINES = {
    "s1.mp3": "It began with a single spark. One artificial neuron, firing in the dark.",
    "s2.mp3": "Then networks learned to learn. Millions of connections, teaching themselves from raw data.",
    "s3.mp3": "With every epoch, the curve climbs. Faster. Sharper. Smarter.",
    "s4.mp3": "From the Turing Test to trillion parameter agents. Seventy years of evolution.",
    "s5.mp3": "AI isn't just a tool anymore. It's becoming smarter... every single day.",
}


async def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for fname, text in LINES.items():
        tts = edge_tts.Communicate(text, VOICE, rate=RATE)
        await tts.save(os.path.join(OUT, fname))
        print(f"[voice] {OUT}/{fname} done")


asyncio.run(main())
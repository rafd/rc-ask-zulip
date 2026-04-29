import re

# Maps bucket name → list of regex patterns (case-insensitive).
# First matching bucket wins; unmatched → "Other".
BUCKETS: dict[str, list[str]] = {
    "AI": [
        r"\bai\b", r"\bllm\b", r"\bmachine.learning\b", r"\bml\b", r"\bneural\b",
        r"\bgpt\b", r"\bembedding\b", r"\btransformer\b", r"\bdiffusion\b",
        r"\bpytorch\b", r"\btensorflow\b", r"\bopenai\b", r"\banthropic\b",
        r"\bclaude\b", r"\brag\b", r"\bvector.search\b",
    ],
    "Games": [
        r"\bgame\b", r"\bgames\b", r"\bgamedev\b", r"\bpygame\b", r"\bunity\b",
        r"\bgodot\b", r"\bshader\b", r"\bengine\b",
    ],
    "Music": [
        r"\bmusic\b", r"\baudio\b", r"\bsynth\b", r"\bmidi\b", r"\bdsp\b",
        r"\bcomposition\b", r"\binstrument\b",
    ],
    "Rust": [
        r"\brust\b", r"\btokio\b", r"\bcargo\b", r"\bborrow.checker\b", r"\bristc\b",
    ],
    "C": [
        r"\bc\b", r"\bclang\b", r"\bc\+\+\b", r"\bcmake\b", r"\bc99\b", r"\bc11\b",
    ],
    "Web": [
        r"\bjavascript\b", r"\btypescript\b", r"\breact\b", r"\bvue\b",
        r"\bsvelte\b", r"\bbrowser\b", r"\bwebassembly\b", r"\bwasm\b",
    ],
    "Python": [
        r"\bpython\b", r"\bdjango\b", r"\bflask\b", r"\bfastapi\b", r"\basyncio\b",
    ],
    "Systems": [
        r"\bkernel\b", r"\bassembly\b", r"\bembedded\b", r"\bfirmware\b",
        r"\boperating.system\b",
    ],
    "Math": [
        r"\bmath\b", r"\bmaths\b", r"\balgebra\b", r"\bcalculus\b",
        r"\bstatistics\b", r"\bprobability\b", r"\bgeometry\b",
    ],
}


def classify(text: str) -> str:
    """Return the first matching bucket name, or 'Other' if none match."""
    for bucket, patterns in BUCKETS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return bucket
    return "Other"

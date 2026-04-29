import re

# Maps bucket name → list of regex patterns (case-insensitive).
# First matching bucket wins; unmatched → "Other".
# Order matters: more specific / higher-signal buckets come first so generic
# words ("game", "data") don't steal messages that are really about AI, etc.
BUCKETS: dict[str, list[str]] = {
    "AI": [
        r"\bai\b", r"\bllm\b", r"\bllms\b", r"\bmachine.learning\b", r"\bml\b",
        r"\bneural\b", r"\bgpt\b", r"\bembedding\b", r"\bembeddings\b",
        r"\btransformer\b", r"\bdiffusion\b", r"\bpytorch\b", r"\btensorflow\b",
        r"\bopenai\b", r"\banthropic\b", r"\bclaude\b", r"\bgemma\b",
        r"\bqwen\b", r"\bllama\b", r"\bollama\b", r"\bmistral\b",
        r"\brag\b", r"\bvector.search\b", r"\bfine.?tun\w*\b",
        r"\binference\b", r"\btraining\s+(?:setup|run|loop|data)\b",
        r"\bagentic\b", r"\bagent\b", r"\bagents\b",
        r"\bcs336\b", r"\bgumbel\b", r"\bbackprop\w*\b",
        r"\bmusicgen\b", r"\btiny\s+language\s+model\b",
        r"\banki\b", r"\bflashcard\w*\b",
    ],
    "Music": [
        r"\bmusic\b", r"\baudio\b", r"\bsynth\w*\b", r"\bmidi\b", r"\bdsp\b",
        r"\bcomposition\b", r"\binstrument\b", r"\bmelod\w+\b",
        r"\bfft\b", r"\bwave\s*shaper\b", r"\brekordbox\b", r"\bdj\b",
        r"\bplaylist\w*\b", r"\bmetronome\b", r"\btuner\b",
        r"\bbeat\b", r"\bsample\s+(?:rate|library)\b",
    ],
    "Games": [
        r"\bgame\b", r"\bgames\b", r"\bgamedev\b", r"\bpygame\b", r"\bunity\b",
        r"\bgodot\b", r"\bshader\w*\b", r"\bgame\s*engine\b",
        r"\barchipelago\b", r"\brandomizer\b", r"\brcade\b",
        r"\bcyberleague\b", r"\bpoker\b", r"\bsettlers\b",
        r"\badvent\s+of\s+code\b", r"\baoc\b", r"\bchess\b",
        r"\broguelike\b", r"\bspeedrun\w*\b",
    ],
    "Rust": [
        r"\brust\b", r"\btokio\b", r"\bcargo\b", r"\bborrow.checker\b",
        r"\brustc\b", r"\bcrate\b", r"\bcrates\b",
    ],
    "Go": [
        r"\bgolang\b", r"\bgoroutine\w*\b", r"\bbyelingual\b",
        r"\blearning\s+go\b", r"\bgo\s+(?:lang|programming|paradigm)\b",
    ],
    "Zig": [
        r"\bzig\b", r"\bzls\b",
    ],
    "C": [
        r"\bc\b", r"\bclang\b", r"\bc\+\+\b", r"\bcmake\b", r"\bc99\b", r"\bc11\b",
        r"\bpointer\s+arithmetic\b", r"\bbitmask\b", r"\bcodegen\b",
    ],
    "Web": [
        r"\bjavascript\b", r"\btypescript\b", r"\breact\b", r"\bvue\b",
        r"\bsvelte\b", r"\bbrowser\b", r"\bwebassembly\b", r"\bwasm\b",
        r"\bnext\.?js\b", r"\bplaywright\b", r"\bhtml\b", r"\bcss\b",
        r"\bfrontend\b", r"\bback.?end\b", r"\bhttp\b",
    ],
    "Python": [
        r"\bpython\b", r"\bdjango\b", r"\bflask\b", r"\bfastapi\b",
        r"\basyncio\b", r"\bpoetry\b", r"\buv\s+(?:init|add|run|sync)\b",
        r"\bpip\b", r"\bpickle\w*\b", r"\bnumpy\b",
    ],
    "Systems": [
        r"\bkernel\b", r"\bassembly\b", r"\bembedded\b", r"\bfirmware\b",
        r"\boperating.system\b", r"\bos\s*:?\s*3\s*easy\s*pieces\b",
        r"\bosteps\b", r"\bmicro\s*vm\w*\b", r"\bvirtual\s+machine\b",
        r"\bcompiler\w*\b", r"\bswapchain\b", r"\bsyscall\w*\b",
        r"\bformal\s+verification\b", r"\blambda\s+calcul\w+\b",
        r"\bdistributed\s+system\w*\b", r"\bmaelstrom\b",
        r"\bgossip\s*glomer\w*\b", r"\bconcurrency\b", r"\bthreading\b",
    ],
    "Math": [
        r"\bmath\b", r"\bmaths\b", r"\balgebra\b", r"\bcalculus\b",
        r"\bstatistics\b", r"\bprobability\b", r"\bgeometry\b",
        r"\btopology\b", r"\bgodel\w*\b", r"\bincompleteness\b",
        r"\bposet\b", r"\bproof\b", r"\bproofs\b",
    ],
    "DevOps": [
        r"\bdevops\b", r"\bci.cd\b", r"\bgithub.actions\b", r"\bjenkins\b",
        r"\bdocker\b", r"\bkubernetes\b", r"\bk8s\b", r"\bk3s\b",
        r"\bterraform\b", r"\bansible\b", r"\bobservability\b",
        r"\bhomelab\b", r"\biac\b", r"\binfrastructure\s+as\s+code\b",
        r"\bcluster\b",
    ],
    "Data": [
        r"\bdata\s+engineering\b", r"\betl\b", r"\bwarehouse\b",
        r"\blakehouse\b", r"\bsql\b", r"\bpandas\b", r"\bpolars\b",
        r"\bspark\b", r"\bduckdb\b", r"\bddia\b",
        r"\bdesigning\s+data.intensive\b", r"\bdataset\w*\b",
    ],
    "Security": [
        r"\bsecurity\b", r"\binfosec\b", r"\bcybersecurity\b", r"\bcrypto\b",
        r"\bencryption\b", r"\bauth\b", r"\boauth\b", r"\bjwt\b",
        r"\bvulnerability\b", r"\bpen.?test\w*\b", r"\brow.?hammer\b",
        r"\bssl\b", r"\btls\b",
    ],
    "Mobile": [
        r"\bmobile\b", r"\bandroid\b", r"\bios\b", r"\bswiftui\b", r"\bswift\b",
        r"\bkotlin\b", r"\breact.native\b", r"\bflutter\b", r"\bxcode\b",
        r"\biphone\b", r"\bipad\b",
    ],
    "Cloud": [
        r"\bcloud\b", r"\baws\b", r"\bazure\b", r"\bgcp\b",
        r"\bserverless\b", r"\blambda\b", r"\bvercel\b", r"\bnetlify\b",
        r"\bmodal\.com\b", r"\bmodal\s+(?:cloud|gpu)\b", r"\bcloud\s+gpu\b",
        r"\bcloudflare\b",
    ],
    "Hardware": [
        r"\bcnc\b", r"\b3d\s*print\w*\b", r"\bsoldering\b", r"\boscilloscope\b",
        r"\barduino\b", r"\braspberry\s*pi\b", r"\bfpga\b",
        r"\binput\s+latency\b", r"\bslow.?mo\b",
    ],
    "Talks/Demos": [
        r"\bgave\s+a\s+talk\b", r"\btalk\b", r"\btalks\b",
        r"\bpresentation\w*\b", r"\bpresented\b", r"\bdemos?\b",
        r"\bhalf.?baked\b", r"\bworkshop\b", r"\blightning\s+talk\b",
        r"\bnon.?tech\s+talk\b",
    ],
    "Pairing": [
        r"\bpaired\b", r"\bpairing\b", r"\bpair\s+(?:with|on|programming)\b",
        r"\bup\s+for\s+pair\w*\b",
    ],
    "Career": [
        r"\bresume\b", r"\bcv\b", r"\bjob\s+search\b", r"\bjobs\s+stuff\b",
        r"\binterview\w*\b", r"\boffer\b", r"\bvolition\b",
    ],
    "Languages": [
        r"\bmandarin\b", r"\bchinese\b", r"\bjapanese\b", r"\bspanish\b",
        r"\bfrench\b", r"\bturkish\b", r"\blinguistic\w*\b",
        r"\bduolingo\b", r"\bidiom\w*\b",
    ],
    "Art": [
        r"\bpaint\w*\b", r"\bcanvas\b", r"\bdrawing\b", r"\billustrat\w+\b",
        r"\bsculpture\b", r"\bgenerative\s+art\b", r"\bifthenpaint\b",
    ],
    "Cooking": [
        r"\bcook\w*\b", r"\brecipe\w*\b", r"\bbaking\b", r"\bbread\b",
        r"\bsalt.{0,4}fat.{0,4}acid.{0,4}heat\b", r"\bcookbook\b",
    ],
    "Life": [
        r"\bsick\b", r"\bcold\b", r"\bcovid\b", r"\bremote\b", r"\brecovery\b",
        r"\bsurgery\b", r"\brepair\w*\b", r"\bappliance\w*\b",
        r"\bmoving\b", r"\bleaving\b", r"\btickets\b", r"\bgoodbye\b",
        r"\bdog\b", r"\bcat\b", r"\bvet\b",
    ],
}


def classify(text: str) -> str:
    """Return the first matching bucket name, or 'Other' if none match."""
    for bucket, patterns in BUCKETS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return bucket
    return "Other"

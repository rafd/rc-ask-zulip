# Main aim:
- ✅ Summarising checkins into groups
- ❌Giving useful answers that summarise the knowledge within Zulip
- ✅ Hosted somewhere = https://checkins.rcdis.co/


# Summarising checkins into groups
1. We SHOULD use OLLAMA as current implementation just uses basic REGEX
    - also have a way of bucketing categories e.g: Bevy & Godot all get bucketed to "Game Dev"

- TBC: Could we extend this beyond check-ins to scope other popular channels?

# Zulip Knowledge:
- ✅ Tweak the prompt to have headings and bullet-point summaries
- ✅ UI = Collapse ALL posts/references
- ✅ Local ollama
- Way to change which OLLAMA model is used
- Stream current progress to the FE

- Show quotes in-line (not whole messages)
- Refactor the schema to have 3 sections.

- 2-Agent pass = Agent1 to write a summary. Agent2 to split that into paragraphs.

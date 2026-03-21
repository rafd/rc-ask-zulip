# Ask RC Zulip

A site to find out what RCers think about certain topics, by searching conversations in Zulip and summarizing with AI.

## Next Up

- sequence diagram
- zulip api search eval
    - do we need to cache Zulip API, or can we use on the fly?
      - how fast is Zulip search API?
      - how good is Zulip search text querying?

## Plan

### UX Flow

- first load:
  - oauth

- initial page:
  - "What do RCers think about..."
  - [ text area ]
  - list of suggested searches / past searches

- result page:
  - log of agent messages
  - final summary

### Architecture

- agentic RAG

- initial prompts
    - system prompt
      - instructions:
        - prompt to do multiple queries, potentially follow up with more queries
      - context:
        - existing channels (?)
      - tools:
        - zulip-search(text, text, text)
    - user prompt

- zulip-search()
  - support multiple text query parameters (to allow bot to issue multiple in one go)
  - TBD based on what zulip API provides
  - we anonymize PII
    - replace user IDs when giving to AI
    - re-replace IDs when displaying to frontend
    - replace emails (yes, easy)
    - replace non-@ name (hard, defer)

- deferring:
  - vector search (would require caching all of Zulip)
  - allowing user to follow up

### Other Choices

- stack: python
- llm-aided-dev: yes

## Misc

- idea to make a zulip "merge topic bot"
- idea to make a zulip "rename topic bot"


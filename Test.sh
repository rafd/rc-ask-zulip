#bin/bash


curl -X POST https://heap-llm.rcdis.co/api/chat/completions \
-H "Authorization: Bearer sk-0171f05e532e42e5bc3f5a29553c414c" \
-H "Content-Type: application/json" \
-d '{
      "model": "gemma3:12b",
      "messages": [
        {
          "role": "user",
          "content": "Why is the sky blue?"
        }
      ]
    }'
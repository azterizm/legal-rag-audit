from jsonpath_ng.ext import parse
import json

data = [
  "conversation_event_created",
  {
    "conversation_id": "bd208096-772e-40a7-bcde-702ad8bdebfc",
    "event": {
      "event_type": "message",
      "created_at": "2026-07-24T06:24:06.070599Z",
      "data": {
        "id": 812540530,
        "content": "Hi! How can I help you today?",
        "author": {
          "type": "ai_assistant"
        }
      }
    }
  }
]

expr = parse("$[?(@.event.event_type=='message' & @.event.data.author.type=='ai_assistant')].event.data.content")
matches = expr.find(data)
if matches:
    print("Match found:", matches[0].value)
else:
    print("No match")

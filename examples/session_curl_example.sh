#!/bin/bash

# Session continuity with curl against the Claude Code OpenAI API Wrapper

echo "Claude Code Session Continuity - curl Example"
echo "================================================="

BASE_URL="http://localhost:8000"
SESSION_ID="curl-demo-session"

# Check server health
echo "Checking server health..."
curl -s "$BASE_URL/health" | jq .
echo ""

# First message - introduce context
echo "1. First message (introducing context):"
echo "Request: Hello! I'm Sarah and I'm learning React."
curl -s -X POST "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"claude-sonnet-5-5\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"Hello! I'm Sarah and I'm learning React.\"}
    ],
    \"session_id\": \"$SESSION_ID\"
  }" | jq -r '.choices[0].message.content'
echo ""

# Second message - test memory
echo "2. Second message (testing memory):"
echo "Request: What's my name and what am I learning?"
curl -s -X POST "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"claude-sonnet-5-5\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"What's my name and what am I learning?\"}
    ],
    \"session_id\": \"$SESSION_ID\"
  }" | jq -r '.choices[0].message.content'
echo ""

# Third message - continue conversation
echo "3. Third message (building on context):"
echo "Request: Can you suggest a simple React project for me?"
curl -s -X POST "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"claude-sonnet-5-5\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"Can you suggest a simple React project for me?\"}
    ],
    \"session_id\": \"$SESSION_ID\"
  }" | jq -r '.choices[0].message.content'
echo ""

# Session management examples
echo "Session Management Examples"
echo "================================"

# List sessions
echo "List all sessions:"
curl -s "$BASE_URL/v1/sessions" | jq .
echo ""

# Get specific session info
echo "Get session info:"
curl -s "$BASE_URL/v1/sessions/$SESSION_ID" | jq .
echo ""

# Get session stats
echo "Session statistics:"
curl -s "$BASE_URL/v1/sessions/stats" | jq .
echo ""

# Streaming example with session
echo "Streaming with session continuity:"
echo "Request: Thanks for your help!"
curl -s -X POST "$BASE_URL/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"claude-sonnet-5-5\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"Thanks for your help!\"}
    ],
    \"session_id\": \"$SESSION_ID\",
    \"stream\": true
  }" | grep '^data: ' | head -5 | jq -r '.choices[0].delta.content // empty' 2>/dev/null | tr -d '\n'
echo ""
echo ""

# Delete session
echo "Cleaning up session:"
curl -s -X DELETE "$BASE_URL/v1/sessions/$SESSION_ID" | jq .
echo ""

echo "curl session example complete."
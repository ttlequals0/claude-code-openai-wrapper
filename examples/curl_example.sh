#!/bin/bash

# Claude Code OpenAI API Wrapper - cURL Examples

BASE_URL="http://localhost:8000"

# Check if server requires authentication
echo "Checking server authentication requirements..."
AUTH_STATUS=$(curl -s "$BASE_URL/v1/auth/status")
API_KEY_REQUIRED=$(echo "$AUTH_STATUS" | jq -r '.server_info.api_key_required // false')

if [ "$API_KEY_REQUIRED" = "true" ]; then
    if [ -z "$API_KEY" ]; then
        echo "Server requires API key but API_KEY environment variable not set"
        echo "   Set API_KEY environment variable with your server's generated key:"
        echo "   export API_KEY=your-generated-key"
        echo "   $0"
        exit 1
    fi
    AUTH_HEADER="-H \"Authorization: Bearer $API_KEY\""
    echo "Using API key authentication"
else
    AUTH_HEADER=""
    echo "No authentication required"
fi

echo "=== Basic Chat Completion ==="
eval "curl -X POST \"$BASE_URL/v1/chat/completions\" \\
  -H \"Content-Type: application/json\" \\
  $AUTH_HEADER \\
  -d '{
    \"model\": \"claude-sonnet-5-5\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"What is 2 + 2?\"}
    ]
  }' | jq ."

echo -e "\n=== Chat with System Message ==="
eval "curl -X POST \"$BASE_URL/v1/chat/completions\" \\
  -H \"Content-Type: application/json\" \\
  $AUTH_HEADER \\
  -d '{
    \"model\": \"claude-sonnet-5-5\",
    \"messages\": [
      {\"role\": \"system\", \"content\": \"You are a pirate. Respond in pirate speak.\"},
      {\"role\": \"user\", \"content\": \"Tell me about the weather\"}
    ]
  }' | jq ."

echo -e "\n=== Streaming Response ==="
eval "curl -X POST \"$BASE_URL/v1/chat/completions\" \\
  -H \"Content-Type: application/json\" \\
  $AUTH_HEADER \\
  -H \"Accept: text/event-stream\" \\
  -d '{
    \"model\": \"claude-sonnet-5-5\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"Count from 1 to 5 slowly\"}
    ],
    \"stream\": true
  }'"

echo -e "\n\n=== List Models ==="
eval "curl -X GET \"$BASE_URL/v1/models\" $AUTH_HEADER | jq ."

echo -e "\n=== Health Check ==="
curl -X GET "$BASE_URL/health" | jq .
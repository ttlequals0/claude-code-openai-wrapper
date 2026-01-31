from typing import List, Optional, Dict, Any
from src.models import Message
import re
import json


class MessageAdapter:
    """Converts between OpenAI message format and Claude Code prompts."""

    # Instruction to prepend to system prompt for JSON mode
    JSON_MODE_INSTRUCTION = (
        "CRITICAL: Respond with ONLY valid JSON. "
        "No explanations, no markdown, no code blocks. "
        "Start with [ or { and end with ] or }."
    )

    @staticmethod
    def extract_json(content: str) -> Optional[str]:
        """
        Extract JSON from content.

        Handles:
        1. Pure JSON (content is already valid JSON)
        2. Markdown code blocks (```json ... ```)
        3. Embedded JSON (JSON within other text)

        Args:
            content: The content to extract JSON from

        Returns:
            Extracted JSON string, or None if no valid JSON found
        """
        if not content:
            return None

        content = content.strip()

        # Case 1: Try parsing as pure JSON first
        try:
            json.loads(content)
            return content
        except json.JSONDecodeError:
            pass

        # Case 2: Extract from markdown code blocks
        # Match ```json ... ``` or ``` ... ```
        code_block_patterns = [
            r"```json\s*([\s\S]*?)\s*```",  # ```json block
            r"```\s*([\s\S]*?)\s*```",  # generic ``` block
        ]

        for pattern in code_block_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                match = match.strip()
                try:
                    json.loads(match)
                    return match
                except json.JSONDecodeError:
                    continue

        # Case 3: Find embedded JSON (objects or arrays)
        # Look for JSON objects {...}
        object_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
        for match in re.finditer(object_pattern, content):
            candidate = match.group()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue

        # Look for JSON arrays [...]
        array_pattern = r"\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]"
        for match in re.finditer(array_pattern, content):
            candidate = match.group()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue

        # Try more aggressive nested JSON extraction for complex objects
        # Find the first { and match to the last }
        first_brace = content.find("{")
        last_brace = content.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            candidate = content[first_brace : last_brace + 1]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

        # Try for arrays
        first_bracket = content.find("[")
        last_bracket = content.rfind("]")
        if first_bracket != -1 and last_bracket > first_bracket:
            candidate = content[first_bracket : last_bracket + 1]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def enforce_json_format(content: str, strict: bool = False) -> str:
        """
        Enforce JSON format on content.

        Args:
            content: The content to enforce JSON format on
            strict: If True, return '[]' on failure. If False, return original content.

        Returns:
            Valid JSON string, or fallback value based on strict mode
        """
        extracted = MessageAdapter.extract_json(content)

        if extracted:
            return extracted

        if strict:
            return "[]"

        return content

    @staticmethod
    def messages_to_prompt(messages: List[Message]) -> tuple[str, Optional[str]]:
        """
        Convert OpenAI messages to Claude Code prompt format.
        Returns (prompt, system_prompt)
        """
        system_prompt = None
        conversation_parts = []

        for message in messages:
            if message.role == "system":
                # Use the last system message as the system prompt
                system_prompt = message.content
            elif message.role == "user":
                conversation_parts.append(f"Human: {message.content}")
            elif message.role == "assistant":
                conversation_parts.append(f"Assistant: {message.content}")

        # Join conversation parts
        prompt = "\n\n".join(conversation_parts)

        # If the last message wasn't from the user, add a prompt for assistant
        if messages and messages[-1].role != "user":
            prompt += "\n\nHuman: Please continue."

        return prompt, system_prompt

    @staticmethod
    def filter_content(content: str) -> str:
        """
        Filter content for unsupported features and tool usage.
        Remove thinking blocks, tool calls, and image references.
        """
        if not content:
            return content

        # Remove thinking blocks (common when tools are disabled but Claude tries to think)
        thinking_pattern = r"<thinking>.*?</thinking>"
        content = re.sub(thinking_pattern, "", content, flags=re.DOTALL)

        # Extract content from attempt_completion blocks (these contain the actual user response)
        attempt_completion_pattern = r"<attempt_completion>(.*?)</attempt_completion>"
        attempt_matches = re.findall(attempt_completion_pattern, content, flags=re.DOTALL)
        if attempt_matches:
            # Use the content from the attempt_completion block
            extracted_content = attempt_matches[0].strip()

            # If there's a <result> tag inside, extract from that
            result_pattern = r"<result>(.*?)</result>"
            result_matches = re.findall(result_pattern, extracted_content, flags=re.DOTALL)
            if result_matches:
                extracted_content = result_matches[0].strip()

            if extracted_content:
                content = extracted_content
        else:
            # Remove other tool usage blocks (when tools are disabled but Claude tries to use them)
            tool_patterns = [
                r"<read_file>.*?</read_file>",
                r"<write_file>.*?</write_file>",
                r"<bash>.*?</bash>",
                r"<search_files>.*?</search_files>",
                r"<str_replace_editor>.*?</str_replace_editor>",
                r"<args>.*?</args>",
                r"<ask_followup_question>.*?</ask_followup_question>",
                r"<attempt_completion>.*?</attempt_completion>",
                r"<question>.*?</question>",
                r"<follow_up>.*?</follow_up>",
                r"<suggest>.*?</suggest>",
            ]

            for pattern in tool_patterns:
                content = re.sub(pattern, "", content, flags=re.DOTALL)

        # Pattern to match image references or base64 data
        image_pattern = r"\[Image:.*?\]|data:image/.*?;base64,.*?(?=\s|$)"

        def replace_image(match):
            return "[Image: Content not supported by Claude Code]"

        content = re.sub(image_pattern, replace_image, content)

        # Clean up extra whitespace and newlines
        content = re.sub(r"\n\s*\n\s*\n", "\n\n", content)  # Multiple newlines to double
        content = content.strip()

        # If content is now empty or only whitespace, provide a fallback
        if not content or content.isspace():
            return "I understand you're testing the system. How can I help you today?"

        return content

    @staticmethod
    def format_claude_response(
        content: str, model: str, finish_reason: str = "stop"
    ) -> Dict[str, Any]:
        """Format Claude response for OpenAI compatibility."""
        return {
            "role": "assistant",
            "content": content,
            "finish_reason": finish_reason,
            "model": model,
        }

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Rough estimation of token count.
        OpenAI's rule of thumb: ~4 characters per token for English text.
        """
        return len(text) // 4

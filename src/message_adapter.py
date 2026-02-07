from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from src.models import Message
import re
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class JsonExtractionResult:
    """Result of JSON extraction with metadata about the extraction process."""
    content: Optional[str]
    success: bool
    method: str  # "direct", "preamble_removed", "code_block", "brace_match", "fallback", "failed"
    original_length: int
    extracted_length: int
    preamble_found: Optional[str] = None


class MessageAdapter:
    """Converts between OpenAI message format and Claude Code prompts."""

    # Instruction to prepend to system prompt for JSON mode
    JSON_MODE_INSTRUCTION = (
        "CRITICAL JSON OUTPUT RULES - FOLLOW EXACTLY:\n"
        "1. Your ENTIRE response must be valid JSON - nothing else\n"
        "2. The FIRST character must be { or [ (no exceptions)\n"
        "3. The LAST character must be } or ] (no exceptions)\n"
        "4. FORBIDDEN: Do NOT write 'Here is the JSON:', 'Here's the response:', or ANY preamble\n"
        "5. FORBIDDEN: Do NOT use markdown code blocks (```)\n"
        "6. FORBIDDEN: Do NOT add any explanation before or after the JSON\n"
        "7. Start typing the JSON immediately - your first keystroke must be { or ["
    )

    # Suffix to append to user prompt to reinforce JSON mode
    JSON_PROMPT_SUFFIX = (
        "\n\n---\n"
        "RESPOND WITH RAW JSON ONLY:\n"
        "- First character: { or [\n"
        "- Last character: } or ]\n"
        "- No preamble like 'Here is...' or 'Here's...'\n"
        "- No markdown, no code fences, no explanation"
    )

    # Common preambles that Claude may add before JSON output
    COMMON_PREAMBLES = [
        "Here's the JSON:",
        "Here is the JSON:",
        "Here's the response:",
        "Here is the response:",
        "Here's your JSON:",
        "Here is your JSON:",
        "Here's the JSON response:",
        "Here is the JSON response:",
        "Here's the data:",
        "Here is the data:",
        "Here's the result:",
        "Here is the result:",
        "Here's the output:",
        "Here is the output:",
        "The JSON is:",
        "JSON response:",
        "Response:",
        "Output:",
        "Result:",
    ]

    @staticmethod
    def _find_balanced_json(content: str, start_char: str, end_char: str) -> Optional[str]:
        """
        Find balanced JSON structure using brace/bracket matching.

        Handles escaped quotes and braces inside strings correctly.

        Args:
            content: The content to search in
            start_char: Opening character ('{' or '[')
            end_char: Closing character ('}' or ']')

        Returns:
            Matched JSON substring or None if not found
        """
        start_idx = content.find(start_char)
        if start_idx == -1:
            return None

        depth = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(content[start_idx:], start=start_idx):
            if escape_next:
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == start_char:
                depth += 1
            elif char == end_char:
                depth -= 1
                if depth == 0:
                    candidate = content[start_idx:i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        # Keep looking for next valid match
                        return None

        return None

    @staticmethod
    def _log_extraction_diagnostics(content: str) -> None:
        """Log diagnostics to help debug JSON extraction failures."""
        logger.debug("=== JSON Extraction Diagnostics ===")

        # Check for code fences
        if "```" in content:
            fence_count = content.count("```")
            logger.debug(f"Found {fence_count} code fence markers (```) in content")
            if fence_count % 2 != 0:
                logger.debug("Odd number of fences - malformed code block?")

        # Check for common preambles
        content_lower = content.lower().strip()
        for preamble in MessageAdapter.COMMON_PREAMBLES:
            if content_lower.startswith(preamble.lower()):
                logger.debug(f"Content starts with preamble: '{preamble}'")
                break

        # Check brace/bracket balance
        open_braces = content.count("{")
        close_braces = content.count("}")
        open_brackets = content.count("[")
        close_brackets = content.count("]")

        logger.debug(f"Brace balance: {{ = {open_braces}, }} = {close_braces}")
        logger.debug(f"Bracket balance: [ = {open_brackets}, ] = {close_brackets}")

        if open_braces != close_braces:
            logger.debug("Unbalanced braces - may indicate truncated or malformed JSON")
        if open_brackets != close_brackets:
            logger.debug("Unbalanced brackets - may indicate truncated or malformed JSON")

        # First and last character analysis
        if content:
            first_char = content[0] if content else ""
            last_char = content[-1] if content else ""
            logger.debug(f"First character: '{first_char}', Last character: '{last_char}'")

            if first_char not in "{[":
                logger.debug("First char is not { or [ - content has preamble or is not JSON")
            if last_char not in "}]":
                logger.debug("Last char is not } or ] - content has suffix or is not JSON")

        # Content preview
        preview_len = 200
        if len(content) > preview_len:
            logger.debug(f"Content preview (first {preview_len}): {content[:preview_len]}...")
            logger.debug(f"Content preview (last 100): ...{content[-100:]}")
        else:
            logger.debug(f"Full content: {content}")

        logger.debug("=== End Diagnostics ===")

    @staticmethod
    def extract_json(content: str) -> Optional[str]:
        """
        Extract JSON from content.

        Priority order:
        1. Pure JSON (content is already valid JSON) - fast path
        2. Preamble removal + parse (strip common Claude preambles)
        3. Markdown code blocks (```json ... ```)
        4. Balanced brace/bracket matching (handles nested structures)
        5. First-to-last fallback (find first { to last })

        Args:
            content: The content to extract JSON from

        Returns:
            Extracted JSON string, or None if no valid JSON found
        """
        if not content:
            logger.debug("extract_json: Empty content")
            return None

        original_content = content
        content = content.strip()

        # Case 1: Try parsing as pure JSON first (fast path)
        try:
            json.loads(content)
            logger.debug(f"extract_json: Already valid JSON ({len(content)} chars)")
            return content
        except json.JSONDecodeError:
            pass

        # Case 2: Try removing common preambles
        content_lower = content.lower()
        for preamble in MessageAdapter.COMMON_PREAMBLES:
            if content_lower.startswith(preamble.lower()):
                stripped = content[len(preamble):].strip()
                try:
                    json.loads(stripped)
                    logger.debug(f"extract_json: Extracted after removing preamble '{preamble}' ({len(stripped)} chars)")
                    return stripped
                except json.JSONDecodeError:
                    # Preamble removed but still not valid - try other methods
                    break

        # Case 3: Extract from markdown code blocks
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
                    logger.debug(f"extract_json: Extracted from code block ({len(match)} chars)")
                    return match
                except json.JSONDecodeError:
                    logger.debug("extract_json: Code block match failed validation")
                    continue

        # Case 4: Balanced brace/bracket matching (new algorithm)
        # Try object first
        balanced_obj = MessageAdapter._find_balanced_json(content, "{", "}")
        if balanced_obj:
            logger.debug(f"extract_json: Extracted via balanced brace matching ({len(balanced_obj)} chars)")
            return balanced_obj

        # Try array
        balanced_arr = MessageAdapter._find_balanced_json(content, "[", "]")
        if balanced_arr:
            logger.debug(f"extract_json: Extracted via balanced bracket matching ({len(balanced_arr)} chars)")
            return balanced_arr

        # Case 5: First-to-last fallback (less precise but handles some edge cases)
        first_brace = content.find("{")
        last_brace = content.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            candidate = content[first_brace : last_brace + 1]
            try:
                json.loads(candidate)
                logger.debug(f"extract_json: Extracted via first-to-last brace ({len(candidate)} chars)")
                return candidate
            except json.JSONDecodeError:
                pass

        first_bracket = content.find("[")
        last_bracket = content.rfind("]")
        if first_bracket != -1 and last_bracket > first_bracket:
            candidate = content[first_bracket : last_bracket + 1]
            try:
                json.loads(candidate)
                logger.debug(f"extract_json: Extracted via first-to-last bracket ({len(candidate)} chars)")
                return candidate
            except json.JSONDecodeError:
                pass

        # Extraction failed - log diagnostics
        logger.warning(f"extract_json: No valid JSON found in {len(content)} chars")
        MessageAdapter._log_extraction_diagnostics(original_content)
        return None

    @staticmethod
    def extract_json_with_metadata(content: str) -> JsonExtractionResult:
        """
        Extract JSON from content and return metadata about the extraction process.

        This method provides detailed information about how the extraction was performed,
        useful for debugging and monitoring.

        Args:
            content: The content to extract JSON from

        Returns:
            JsonExtractionResult with extraction details
        """
        if not content:
            return JsonExtractionResult(
                content=None,
                success=False,
                method="failed",
                original_length=0,
                extracted_length=0,
            )

        original_length = len(content)
        content = content.strip()

        # Case 1: Try parsing as pure JSON first (fast path)
        try:
            json.loads(content)
            return JsonExtractionResult(
                content=content,
                success=True,
                method="direct",
                original_length=original_length,
                extracted_length=len(content),
            )
        except json.JSONDecodeError:
            pass

        # Case 2: Try removing common preambles
        content_lower = content.lower()
        for preamble in MessageAdapter.COMMON_PREAMBLES:
            if content_lower.startswith(preamble.lower()):
                stripped = content[len(preamble):].strip()
                try:
                    json.loads(stripped)
                    return JsonExtractionResult(
                        content=stripped,
                        success=True,
                        method="preamble_removed",
                        original_length=original_length,
                        extracted_length=len(stripped),
                        preamble_found=preamble,
                    )
                except json.JSONDecodeError:
                    break

        # Case 3: Extract from markdown code blocks
        code_block_patterns = [
            r"```json\s*([\s\S]*?)\s*```",
            r"```\s*([\s\S]*?)\s*```",
        ]

        for pattern in code_block_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                match = match.strip()
                try:
                    json.loads(match)
                    return JsonExtractionResult(
                        content=match,
                        success=True,
                        method="code_block",
                        original_length=original_length,
                        extracted_length=len(match),
                    )
                except json.JSONDecodeError:
                    continue

        # Case 4: Balanced brace/bracket matching
        balanced_obj = MessageAdapter._find_balanced_json(content, "{", "}")
        if balanced_obj:
            return JsonExtractionResult(
                content=balanced_obj,
                success=True,
                method="brace_match",
                original_length=original_length,
                extracted_length=len(balanced_obj),
            )

        balanced_arr = MessageAdapter._find_balanced_json(content, "[", "]")
        if balanced_arr:
            return JsonExtractionResult(
                content=balanced_arr,
                success=True,
                method="brace_match",
                original_length=original_length,
                extracted_length=len(balanced_arr),
            )

        # Case 5: First-to-last fallback
        first_brace = content.find("{")
        last_brace = content.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            candidate = content[first_brace : last_brace + 1]
            try:
                json.loads(candidate)
                return JsonExtractionResult(
                    content=candidate,
                    success=True,
                    method="fallback",
                    original_length=original_length,
                    extracted_length=len(candidate),
                )
            except json.JSONDecodeError:
                pass

        first_bracket = content.find("[")
        last_bracket = content.rfind("]")
        if first_bracket != -1 and last_bracket > first_bracket:
            candidate = content[first_bracket : last_bracket + 1]
            try:
                json.loads(candidate)
                return JsonExtractionResult(
                    content=candidate,
                    success=True,
                    method="fallback",
                    original_length=original_length,
                    extracted_length=len(candidate),
                )
            except json.JSONDecodeError:
                pass

        # Failed
        return JsonExtractionResult(
            content=None,
            success=False,
            method="failed",
            original_length=original_length,
            extracted_length=0,
        )

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
            logger.debug(f"enforce_json_format: Successfully extracted ({len(extracted)} chars)")
            return extracted

        logger.warning(f"enforce_json_format: Extraction failed, strict={strict}")
        if strict:
            return "[]"

        return content

    @staticmethod
    def enforce_json_format_with_metadata(content: str, strict: bool = False) -> Tuple[str, Dict[str, Any]]:
        """
        Enforce JSON format on content and return metadata about the extraction.

        Args:
            content: The content to enforce JSON format on
            strict: If True, return '[]' on failure. If False, return original content.

        Returns:
            Tuple of (extracted_content, metadata_dict)
        """
        result = MessageAdapter.extract_json_with_metadata(content)

        metadata = {
            "success": result.success,
            "method": result.method,
            "original_length": result.original_length,
            "extracted_length": result.extracted_length,
            "preamble_found": result.preamble_found,
            "strict_mode": strict,
        }

        if result.success and result.content:
            logger.debug(f"enforce_json_format_with_metadata: method={result.method}, "
                        f"original={result.original_length}, extracted={result.extracted_length}")
            if result.preamble_found:
                logger.debug(f"enforce_json_format_with_metadata: removed preamble '{result.preamble_found}'")
            return result.content, metadata

        logger.warning(f"enforce_json_format_with_metadata: Extraction failed, strict={strict}")
        metadata["fallback_used"] = True

        if strict:
            metadata["fallback_value"] = "[]"
            return "[]", metadata

        return content, metadata

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

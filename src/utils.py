"""Utility functions for OpenMetaMind."""

import re
import logging

logger = logging.getLogger(__name__)


def strip_think(text: str) -> str:
    """Remove chain-of-thought (<think>...) from text.
    
    This sanitizes LLM outputs by removing any CoT tokens and their contents.
    Should be applied to all LLM outputs before:
    - storing in AgentFinding.summary
    - generating ProposedAction descriptions
    - rendering in UI
    
    Args:
        text: Raw text that may contain <think> blocks
        
    Returns:
        Clean text with all <think> blocks removed
    """
    if not text:
        return text
    
    # Remove think blocks using a function to handle unicode properly
    def remove_think_blocks(s):
        result = s
        while '<think>' in result:
            start = result.find('<think>')
            end = result.find('》', start)
            if end == -1:
                result = result[:start]
            else:
                result = result[:start] + result[end + 5:]
        return result
    
    cleaned = remove_think_blocks(text)
    
    return cleaned.strip()


def sanitize_for_display(text: str) -> str:
    """Sanitize text for safe display in UI.
    
    Applies strip_think and also handles other potentially problematic content.
    
    Args:
        text: Text to sanitize
        
    Returns:
        Safe text for display
    """
    if not text:
        return text
    
    # First strip any CoT
    text = strip_think(text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def sanitize_json_string(text: str) -> str:
    """Sanitize a string intended for JSON embedding.
    
    Escapes special characters that could break JSON parsing.
    
    Args:
        text: Text to sanitize for JSON
        
    Returns:
        JSON-safe string
    """
    if not text:
        return text
    
    # Remove CoT first
    text = strip_think(text)
    
    # Escape JSON-sensitive characters
    text = text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    
    return text
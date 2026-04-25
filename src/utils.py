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
    
    # Use regex to remove all think blocks - handles various closing tag formats
    # Pattern matches <think> followed by any characters until one of the closing tags
    cleaned = re.sub(
        r'<think>[\s\S]*?(?:』|】|<\/think>)',
        '',
        text
    )
    
    return cleaned.strip()
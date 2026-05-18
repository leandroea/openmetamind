"""Utility functions for OpenMetaMind."""

import re
import logging

logger = logging.getLogger(__name__)


def strip_think(text: str) -> str:
    """Remove chain-of-thought (<think>...</think>) from text.
    
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
    
    # Remove all <think>...</think> blocks (non-greedy, across newlines)
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    
    return cleaned.strip()
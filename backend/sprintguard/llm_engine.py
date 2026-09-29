"""
LLM engine for problem statement analysis and story generation.
Model loading, text generation, and JSON parsing.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from .config import SNAPSHOT_PATH, MAX_NEW_TOKENS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Global model instances
_tokenizer = None
_model = None


def validate_snapshot_path() -> None:
    """Validate that the model snapshot path exists and has required files."""
    path = Path(SNAPSHOT_PATH)
    if not path.exists():
        raise FileNotFoundError(f"Local Llama snapshot path not found: {SNAPSHOT_PATH}")

    if not (path / "config.json").exists():
        raise FileNotFoundError(f"Local Llama snapshot is missing config.json: {SNAPSHOT_PATH}")

    tokenizer_present = any(
        (path / filename).exists()
        for filename in ["tokenizer.json", "tokenizer.model", "tokenizer_config.json"]
    )
    if not tokenizer_present:
        raise FileNotFoundError(
            "Local Llama snapshot is missing tokenizer files. Expected one of: "
            "tokenizer.json, tokenizer.model, tokenizer_config.json. "
            f"Snapshot path: {SNAPSHOT_PATH}"
        )


def get_llm_model_and_tokenizer() -> Tuple[Any, Any]:
    """Load and cache the LLM model and tokenizer."""
    global _tokenizer, _model

    if _tokenizer is not None and _model is not None:
        return _tokenizer, _model

    validate_snapshot_path()

    tokenizer = AutoTokenizer.from_pretrained(
        SNAPSHOT_PATH,
        local_files_only=True,
        use_fast=True,
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    dtype = torch.float16 if torch.cuda.is_available() else torch.float32

    model = AutoModelForCausalLM.from_pretrained(
        SNAPSHOT_PATH,
        local_files_only=True,
        torch_dtype=dtype,
        low_cpu_mem_usage=True,
    )

    model = model.to("cuda" if torch.cuda.is_available() else "cpu")
    model.eval()

    _tokenizer = tokenizer
    _model = model
    return _tokenizer, _model


def generate_with_llama(prompt: str) -> str:
    """Generate text using the Llama model."""
    tokenizer, model = get_llm_model_and_tokenizer()
    device = next(model.parameters()).device

    # Concise system prompt for JSON output
    system_content = "You are an AI that outputs ONLY valid JSON. Start with { and end with }. No explanations."

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt},
    ]

    if hasattr(tokenizer, "apply_chat_template"):
        input_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    else:
        input_text = prompt

    inputs = tokenizer(input_text, return_tensors="pt", truncation=True, max_length=4096)
    inputs = {key: value.to(device) for key, value in inputs.items()}

    # Use deterministic generation for reliable JSON output
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,  # Deterministic generation for consistent JSON
            num_beams=1,
            repetition_penalty=1.1,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    generated_ids = output_ids[0][inputs["input_ids"].shape[-1]:]
    raw_output = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
    
    # Log the raw output for debugging
    logger.info(f"LLM raw output length: {len(raw_output)} chars")
    logger.debug(f"LLM raw output (first 500 chars): {raw_output[:500]}")
    
    return raw_output


def remove_trailing_commas(text: str) -> str:
    """Remove trailing commas before ] or } which are invalid in JSON."""
    text = re.sub(r',(\s*[\]}])', r'\1', text)
    return text


def _extract_json_with_brace_balancing(text: str) -> Optional[str]:
    """
    Extract JSON object using brace balancing.
    More robust than regex for truncated or malformed JSON.
    """
    # Find the first opening brace
    start = text.find('{')
    if start == -1:
        return None
    
    depth = 0
    in_string = False
    escape_next = False
    end = start
    
    for i, char in enumerate(text[start:], start):
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
            
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                return text[start:end]
    
    # If we exit the loop without finding balanced braces,
    # the JSON is truncated - try to repair it
    if depth > 0:
        # Return the partial JSON for repair attempt
        return text[start:]
    
    return None


def _repair_truncated_json(text: str) -> Optional[str]:
    """
    Attempt to repair truncated JSON by closing unclosed structures.
    """
    if not text:
        return None
    
    # Count unclosed braces and brackets
    depth_brace = 0
    depth_bracket = 0
    in_string = False
    escape_next = False
    
    for char in text:
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
        if char == '{':
            depth_brace += 1
        elif char == '}':
            depth_brace -= 1
        elif char == '[':
            depth_bracket += 1
        elif char == ']':
            depth_bracket -= 1
    
    # If we're inside an unclosed string, try to close it
    if in_string:
        text = text.rstrip()
        # Remove incomplete string value
        if text.endswith(','):
            text = text[:-1]
        text += '"'
    
    # Remove trailing comma if present
    text = text.rstrip()
    if text.endswith(','):
        text = text[:-1]
    
    # Close unclosed brackets and braces
    text += ']' * max(0, depth_bracket)
    text += '}' * max(0, depth_brace)
    
    return text


def _try_json_repair_library(text: str) -> Optional[Dict[str, Any]]:
    """
    Try to use json_repair library if available for more sophisticated repair.
    """
    try:
        from json_repair import repair_json
        repaired = repair_json(text)
        return json.loads(repaired)
    except ImportError:
        logger.debug("json_repair library not installed, using built-in repair")
        return None
    except Exception as e:
        logger.debug(f"json_repair failed: {e}")
        return None


def extract_first_json_object(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract the first valid JSON object from text using multiple strategies:
    1. Brace-balancing extraction
    2. Built-in truncation repair
    3. json_repair library (if available)
    4. Regex fallback
    """
    if not text:
        logger.warning("Empty text provided to extract_first_json_object")
        return None
    
    # Log raw input for debugging
    logger.info(f"Attempting to extract JSON from text of length {len(text)}")
    
    # Remove markdown code fences if present
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```\s*$', '', text, flags=re.MULTILINE)
    text = text.strip()
    
    # Strategy 1: Try brace-balancing extraction
    candidate = _extract_json_with_brace_balancing(text)
    
    if candidate:
        # Clean up the candidate
        candidate = remove_trailing_commas(candidate)
        
        # Try to parse directly
        try:
            result = json.loads(candidate)
            logger.info("JSON parsed successfully with brace-balancing")
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"Brace-balanced JSON invalid: {e}")
            
            # Strategy 2: Try built-in repair
            repaired = _repair_truncated_json(candidate)
            if repaired:
                repaired = remove_trailing_commas(repaired)
                try:
                    result = json.loads(repaired)
                    logger.info("JSON parsed successfully after built-in repair")
                    return result
                except json.JSONDecodeError as e2:
                    logger.warning(f"Built-in repair failed: {e2}")
            
            # Strategy 3: Try json_repair library
            result = _try_json_repair_library(candidate)
            if result:
                logger.info("JSON parsed successfully with json_repair library")
                return result
    
    # Strategy 4: Fallback to simple regex (last resort)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        candidate = match.group(0)
        candidate = remove_trailing_commas(candidate)
        try:
            result = json.loads(candidate)
            logger.info("JSON parsed successfully with regex fallback")
            return result
        except json.JSONDecodeError as e:
            logger.error(f"All JSON extraction strategies failed. Last error: {e}")
            logger.error(f"Raw text (first 1000 chars): {text[:1000]}")
    else:
        logger.error("No JSON-like structure found in text")
        logger.error(f"Raw text (first 500 chars): {text[:500]}")
    
    return None

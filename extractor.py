"""LLM recipe extraction via Anthropic tool-use (guarantees structured JSON)."""
from __future__ import annotations

import anthropic

DEFAULT_MODEL = "claude-sonnet-5-5"

RECIPE_TOOL = {
    "name": "save_recipe",
    "description": "Save the structured recipe extracted from the cooking video transcript.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Recipe name"},
            "description": {"type": "string", "description": "1-2 sentence summary"},
            "preparationTime": {"type": "string", "description": "Prep time in minutes, digits only (e.g. '15'); '' if unknown"},
            "cookingTime": {"type": "string", "description": "Cook time in minutes, digits only; '' if unknown"},
            "totalTime": {"type": "integer", "description": "Total time in minutes; 0 if unknown"},
            "quantity": {"type": "string", "description": "Servings, e.g. '4 servings'"},
            "category": {"type": "string", "description": "Primary course/category, e.g. 'Main course', 'Dessert'"},
            "cookware": {"type": "array", "items": {"type": "string"}, "description": "Pans, tools, appliances needed"},
            "ingredients": {"type": "array", "items": {"type": "string"}, "description": "One entry per ingredient, with measurements, e.g. '200 g flour'"},
            "instructions": {"type": "array", "items": {"type": "string"}, "description": "One entry per step, in order, without numbering"},
        },
        "required": ["title", "description", "preparationTime", "cookingTime", "totalTime",
                     "quantity", "category", "cookware", "ingredients", "instructions"],
    },
}

SYSTEM = (
    "You extract clean, cookable recipes from noisy YouTube cooking-video transcripts. "
    "Remove filler, sponsor segments and chit-chat. Only use information present in the "
    "transcript; if an amount or time is not stated, give a sensible estimate only for times, "
    "and leave ingredient amounts out rather than inventing them. Write the recipe in the "
    "language of the transcript. Always answer by calling save_recipe."
)


def extract_recipe(transcript: str, api_key: str, model: str = DEFAULT_MODEL,
                   video_title: str = "") -> dict:
    client = anthropic.Anthropic(api_key=api_key)
    transcript = transcript[:150_000]  # safety cap
    msg = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM,
        tools=[RECIPE_TOOL],
        tool_choice={"type": "tool", "name": "save_recipe"},
        messages=[{"role": "user", "content": f"Video title: {video_title or 'unknown'}\n\nTranscript:\n{transcript}"}],
    )
    for block in msg.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("The model did not return a recipe.")

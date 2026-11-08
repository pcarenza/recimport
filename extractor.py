"""LLM recipe extraction via Google Gemini (structured JSON output)."""
from __future__ import annotations

import json

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field

DEFAULT_MODEL = "gemini-3.8-flash"
FALLBACK_MODELS = ("gemini-3.8-flash", "gemini-flash-latest")


class Recipe(BaseModel):
    title: str = Field(description="Recipe name")
    description: str = Field(description="1-2 sentence summary")
    preparationTime: str = Field(description="Prep time in minutes, digits only (e.g. '15'); '' if unknown")
    cookingTime: str = Field(description="Cook time in minutes, digits only; '' if unknown")
    totalTime: int = Field(description="Total time in minutes; 0 if unknown")
    quantity: str = Field(description="Servings, e.g. '4 servings'")
    category: str = Field(description="Primary course/category, e.g. 'Main course', 'Dessert'")
    cookware: list[str] = Field(description="Pans, tools, appliances needed")
    ingredients: list[str] = Field(description="One entry per ingredient, with measurements, e.g. '200 g flour'")
    instructions: list[str] = Field(description="One entry per step, in order, without numbering")


SYSTEM = (
    "You extract clean, cookable recipes from noisy YouTube cooking-video transcripts. "
    "Remove filler, sponsor segments and chit-chat. Only use information present in the "
    "transcript; if an amount or time is not stated, give a sensible estimate only for times, "
    "and leave ingredient amounts out rather than inventing them. Write the recipe in the "
    "language of the transcript."
)


def extract_recipe(transcript: str, api_key: str, model: str = DEFAULT_MODEL,
                   video_title: str = "") -> dict:
    client = genai.Client(api_key=api_key)
    contents = f"Video title: {video_title or 'unknown'}\n\nTranscript:\n{transcript[:500_000]}"
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        response_mime_type="application/json",
        response_schema=Recipe,
        temperature=0.2,
    )
    # Model names get retired often: if the chosen one 404s, try the fallbacks.
    resp, last_err = None, None
    for m in dict.fromkeys((model, *FALLBACK_MODELS)):
        try:
            resp = client.models.generate_content(model=m, contents=contents, config=config)
            break
        except errors.ClientError as e:
            if e.code != 404:
                raise
            last_err = e
    if resp is None:
        raise last_err
    if resp.parsed is not None:
        return resp.parsed.model_dump()
    if resp.text:
        return json.loads(resp.text)
    raise RuntimeError("Gemini did not return a recipe (possibly blocked by safety filters).")

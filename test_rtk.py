import io, json, zipfile
from rtk import build_recipe, build_rtk, extract_video_id

def test_ids():
    for u in ["https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=3", "https://youtu.be/dQw4w9WgXcQ?si=x",
              "youtube.com/shorts/dQw4w9WgXcQ", "https://m.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"]:
        assert extract_video_id(u) == "dQw4w9WgXcQ"

def test_rtk():
    data = {"title": "Pasta", "category": "Main", "preparationTime": "10 min", "cookingTime": "20",
            "totalTime": 30, "quantity": "4 servings", "cookware": ["pot"],
            "ingredients": ["200 g pasta", "salt"], "instructions": ["Boil", "Drain"]}
    r, rid = build_recipe(data, "https://youtu.be/x", b"png")
    z = zipfile.ZipFile(io.BytesIO(build_rtk(r, b"png")))
    assert set(z.namelist()) == {"recipes_0.json", "categories.json", "tags.json", "calendar.json", f"{rid}.png"}
    rec = json.loads(z.read("recipes_0.json"))[0]
    assert rec["ingredients"] == "200 g pasta\nsalt" and rec["instructions"] == "Boil\nDrain"
    assert rec["totalTime"] == 30 and rec["preparationTime"] == "10" and rec["pictures"] == [f"{rid}.png"]

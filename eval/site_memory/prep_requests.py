"""The request sets of a run of the site's memory under load, placed by module 1's rules of the tree (no model loaded): which ask the open model, and
the product type each lands on. usage: run from a tree: python prep_requests.py <out.json>"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from engine import web  # noqa: E402
from engine.query import PRODUCT_TYPES  # noqa: E402

BIG_A = ["blush that stays on all day for fair skin", "mascara that does not smudge under my eyes",
         "full coverage foundation for oily skin in summer", "noise cancelling headphones for long flights",
         "wireless earbuds that stay in while running", "cordless drill for occasional diy at home",
         "laptop for a university student on a budget", "moisturiser for combination skin under makeup"]
BIG_B = ["sunscreen for darker skin that leaves no cast", "cleanser for dry sensitive skin in winter",
         "shampoo for thin fine hair that gets greasy", "toner for large pores and oily t-zone",
         "quiet dishwasher for an open plan flat", "enamel dutch oven for bread baking",
         "burr coffee grinder for espresso at home", "fridge freezer that is reliable and quiet"]
MODEL_TRY = ["something nice for my mum", "a gift for my dad who has everything", "what should I get my sister for her birthday",
             "present for a friend who loves cooking", "need something for my skin its been really dry lately",
             "my hair is a mess help", "stuff for my new flat", "what do I need for my first kitchen",
             "something to help me sleep better", "my face gets shiny by noon", "help with frizz in humid weather",
             "anything for tired looking eyes", "gift for a coworker under 30", "a treat for myself after exams",
             "something for chapped hands from washing up", "thing to keep coffee hot at my desk",
             "I keep burning my rice", "my knives are always blunt", "make my bathroom feel like a spa",
             "my scalp itches all the time", "what helps with redness on cheeks", "need a gift for a gardener",
             "what to buy a new mum", "my lips crack every winter", "upgrade my morning routine",
             "serum", "cream", "something for spots", "a nice smelling thing for the house", "kit for a beginner baker",
             "help my skin glow", "my pans keep sticking", "a good everyday bag", "for my oily face",
             "something gentle", "best one for travel", "need new pots", "I sweat a lot", "anything for dark circles",
             "a present for a teenager"]
MODS = ["best {t}", "{t} for beginners", "cheap {t} that lasts", "{t} under 100", "most durable {t}", "{t} recommendations",
        "which {t} should I buy", "{t} for a small flat", "quiet {t}", "{t} for a gift", "premium {t} worth it",
        "{t} that is easy to clean", "{t} for sensitive people", "long lasting {t}", "{t} for everyday use"]


def placed(text):
    return web._placed_by_rules(text)


out = {"big_a": [], "big_b": [], "model": [], "soak": []}
for key, texts in (("big_a", BIG_A), ("big_b", BIG_B)):
    for t in texts:
        out[key].append({"text": t, "type": placed(t)[0], "asks_model": placed(t)[1]})
out["model"] = [t for t in MODEL_TRY if placed(t)[1]]
warm = set(web.warm_requests())
rng = random.Random(20261105)
types = [p.name for p in PRODUCT_TYPES]
soak, kinds = [], set()
for _ in range(9000):
    t = rng.choice(types)
    text = rng.choice(MODS).format(t=t)
    if text in warm or text in soak:
        continue
    soak.append(text)
rng.shuffle(soak)
out["soak"] = soak[:5000]
out["n_types"] = len(types)
out["warm"] = len(warm)
print({k: (len(v) if isinstance(v, list) else v) for k, v in out.items()})
print("big_a", [(r["type"], r["asks_model"]) for r in out["big_a"]])
print("big_b", [(r["type"], r["asks_model"]) for r in out["big_b"]])
print("model", out["model"])
Path(sys.argv[1]).write_text(json.dumps(out, indent=1))

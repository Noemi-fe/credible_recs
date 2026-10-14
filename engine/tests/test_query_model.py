"""Module 1's second opinion: a free open model for the requests the rules can't route (Noemi, 11 Oct 2026).

The rules stay first; the model is asked only when they find no product type, and its answer is checked by code. Every
test here uses a stand-in model: no test loads the real one (engine/tests/conftest.py turns it off).
"""

import importlib.abc
import sys
import threading
import time
from pathlib import Path

from engine.config import SUBREDDITS
from engine.query import parse_query
from engine.query_model import LlamaQueryModel


class FakeModel:
    """Answers every request with the same fields, and remembers what it was asked."""

    def __init__(self, answer):
        self.answer = answer
        self.asked: list[str] = []

    def read(self, text: str):
        self.asked.append(text)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_the_rules_go_first_and_the_model_isnt_asked_when_they_route_a_request():
    model = FakeModel({"category": "kitchen", "product": "kettle"})
    query = parse_query("gentle cleanser for acne-prone skin", model=model)
    assert (query.status, query.product_type) == ("ok", "cleanser")
    assert model.asked == []


# Changed on purpose 14 Oct 2026 (kitchen appliances, Noemi's decision 3): the air fryer and the rice cooker, the
# examples below until then, are module 1's own types now, routed by the rules without the model
# (engine/tests/test_query_appliances.py). A bread maker is still one the rules don't know.

def test_a_kitchen_product_the_rules_dont_know_becomes_a_product_type_of_its_own():
    query = parse_query("bread maker that lasts, under £100",
                        model=FakeModel({"category": "kitchen", "product": "bread maker"}))
    assert (query.status, query.category, query.product_type) == ("ok", "kitchen", "bread maker")
    assert query.subreddits == list(SUBREDDITS["kitchen"])
    assert query.constraints.budget.max == 100  # budgets and units are still read by the rules
    assert query.search_terms and "bread maker" in query.search_terms[-1]


def test_a_plural_in_the_request_still_counts_as_its_own_words():
    query = parse_query("best bread makers for sourdough", model=FakeModel({"category": "kitchen", "product": "bread maker"}))
    assert (query.status, query.product_type) == ("ok", "bread maker")


def test_an_appliance_the_rules_route_never_asks_the_model():
    model = FakeModel({"category": "kitchen", "product": "kettle"})
    query = parse_query("air fryer that lasts, under £100", model=model)
    assert (query.status, query.product_type) == ("ok", "air fryer") and model.asked == []


def test_a_product_the_request_doesnt_name_is_never_used():
    # A vague request stays a question: the model can't turn "something nice for my mum" into a gift set.
    query = parse_query("something nice for my mum", model=FakeModel({"category": "kitchen", "product": "gift set"}))
    assert query.status == "clarify" and query.product_type is None


def test_a_generic_word_is_not_a_product():
    query = parse_query("best gadget for my kitchen", model=FakeModel({"category": "kitchen", "product": "gadget"}))
    assert query.status == "clarify"


def test_a_request_the_model_puts_outside_our_categories_gets_the_polite_no():
    query = parse_query("best yoga mat for beginners", model=FakeModel({"category": "other", "product": "yoga mat"}))
    assert query.status == "out_of_scope" and "skincare, haircare and kitchen" in query.message


def test_an_unclear_broken_or_failing_answer_leaves_the_rules_question():
    for answer in ({"category": "unclear", "product": ""}, {"category": "garden", "product": "hose"}, "not json",
                   None, RuntimeError("the model crashed")):
        query = parse_query("best hose reel", model=FakeModel(answer))
        assert query.status == "clarify", answer


def test_two_products_stay_a_question_and_the_model_isnt_asked():
    model = FakeModel({"category": "kitchen", "product": "kettle"})
    query = parse_query("kettle and chef knife", model=model)
    assert query.status == "clarify" and model.asked == []


def test_without_a_model_nothing_changes():
    # Tests run with the real model turned off (conftest): the rules alone ask what kind of product.
    assert parse_query("bread maker that lasts").status == "clarify"


def test_a_word_for_a_category_or_a_place_is_not_a_product():
    # "kitchen gadget" or "hair products" say where or what for, not what: the question stands.
    for text, product in (("best kitchen gadget", "kitchen gadget"), ("hair products for curls", "hair product"),
                          ("best skincare for my 30s", "skincare")):
        category = "haircare" if "hair" in text else "kitchen" if "kitchen" in text else "skincare"
        query = parse_query(text, model=FakeModel({"category": category, "product": product}))
        assert query.status == "clarify", text


def test_a_lookalike_the_rules_leave_to_the_model_is_placed_by_it():
    # "cream" in "ice cream maker" isn't a moisturiser: the rules ask, and the model places it in the kitchen.
    query = parse_query("ice cream maker that lasts", model=FakeModel({"category": "kitchen", "product": "ice cream maker"}))
    assert (query.status, query.category, query.product_type) == ("ok", "kitchen", "ice cream maker")
    query = parse_query("vacuum sealer for sous vide", model=FakeModel({"category": "kitchen", "product": "vacuum sealer"}))
    assert (query.status, query.category, query.product_type) == ("ok", "kitchen", "vacuum sealer")


def test_the_model_can_place_a_haircare_product():
    query = parse_query("heat protectant spray for fine hair", model=FakeModel({"category": "haircare", "product": "heat protectant spray"}))
    assert (query.status, query.category, query.product_type) == ("ok", "haircare", "heat protectant spray")
    assert query.subreddits == list(SUBREDDITS["haircare"])


class _OneAtATime:
    """A stand-in for llama.cpp that notices when two requests use it at once."""

    def __init__(self):
        self.busy = False
        self.overlapped = False

    def create_chat_completion(self, **_):
        if self.busy:
            self.overlapped = True
        self.busy = True
        time.sleep(0.02)
        self.busy = False
        return {"choices": [{"message": {"content": '{"category": "kitchen", "product": "toaster"}'}}]}


def test_the_open_model_answers_one_request_at_a_time():
    # The web server answers requests in parallel; llama.cpp can't be used by two of them at once.
    model = LlamaQueryModel(Path("not-loaded.gguf"))
    model._llm = _OneAtATime()
    workers = [threading.Thread(target=model.read, args=("toaster",)) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    assert not model._llm.overlapped


class _BrokenLlama(importlib.abc.MetaPathFinder):
    """Makes `import llama_cpp` fail the way a missing system library does (an OSError, not an ImportError)."""

    def find_spec(self, name, path, target=None):
        if name == "llama_cpp":
            raise OSError("libgomp.so.1: cannot open shared object file")
        return None


def test_a_model_library_that_fails_to_load_leaves_the_rules_alone(tmp_path, monkeypatch):
    # Found at the Space package's review (11 Oct 2026): only a missing package was caught, so a llama.cpp that can't
    # load its system library would have broken every request instead of falling back to the rules.
    from engine import query_model

    weights = tmp_path / "model.gguf"
    weights.write_bytes(b"not a real model")
    monkeypatch.setattr(query_model, "DEFAULT_MODEL_PATH", weights)
    monkeypatch.delenv(query_model.SWITCH, raising=False)
    monkeypatch.delitem(sys.modules, "llama_cpp", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_BrokenLlama(), *sys.meta_path])
    assert query_model.find_default_model() is None


def test_a_clue_word_for_a_part_doesnt_decide_when_the_model_names_the_product():
    # 11 Oct 2026, from the appliance builder's findings: "pot" in "rice cooker with a non-stick pot" is a part of a
    # rice cooker, not a saucepan. When the rules place a request by a clue word alone, the model is asked too.
    query = parse_query("rice cooker with a non-stick pot", model=FakeModel({"category": "kitchen", "product": "rice cooker"}))
    assert (query.status, query.product_type) == ("ok", "rice cooker")


def test_a_clue_word_the_model_agrees_with_stands():
    assert parse_query("pot for pasta", model=FakeModel({"category": "kitchen", "product": "pot"})).product_type == "saucepan"
    stainless = FakeModel({"category": "kitchen", "product": "stainless pot"})
    assert parse_query("stainless pot for soup", model=stainless).product_type == "saucepan"
    unsure = FakeModel({"category": "unclear", "product": ""})
    assert parse_query("pot for pasta", model=unsure).product_type == "saucepan"
    # Changed on purpose 14 Oct 2026: the rice cooker is module 1's own type now, so the rules alone place "rice cooker
    # with a non-stick pot" (it was a saucepan, by the clue word "pot"); a bread maker's pot is still a clue alone.
    assert parse_query("bread maker with a non-stick pot", model=None).product_type == "saucepan"  # rules alone
    assert parse_query("rice cooker with a non-stick pot", model=None).product_type == "rice cooker"


class _Counting:
    """A stand-in for llama.cpp that counts the readings it is asked for."""

    def __init__(self):
        self.calls = []

    def create_chat_completion(self, messages, **_):
        self.calls.append(messages[-1]["content"])
        return {"choices": [{"message": {"content": '{"category": "kitchen", "product": "toaster"}'}}]}


def test_a_request_read_before_is_answered_without_asking_the_model_again():
    # Its answer for the same words never changes (temperature 0): the server gets ready by answering every product
    # type, and a visitor asking one of them again needn't wait for the model (latency, 13 Oct 2026).
    model = LlamaQueryModel(Path("not-loaded.gguf"))
    model._llm = _Counting()
    first = model.read("toaster")
    first["product"] = "changed by the caller"
    assert model.read("toaster") == {"category": "kitchen", "product": "toaster"}
    assert model._llm.calls == ["toaster"]
    model.read("best toaster for a small kitchen")
    assert model._llm.calls == ["toaster", "best toaster for a small kitchen"]

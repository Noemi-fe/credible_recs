"""Smaller objects for the library the site keeps in memory (5 Nov 2026, the site-memory builder, after Noemi's "Let's do A").

Every pydantic object keeps `__pydantic_fields_set__`, the set of the names of the fields it was given. A set of nine
or ten names has 32 slots and takes 728 bytes, as much as everything else a comment holds once its words are gone. The
library holds 213,000 comments, 93,000 writers and about as many mentions again. Measured on 5 Nov 2026, those sets were
about a quarter of the library's memory, some 250 MB of the site's 1.9 GiB.

The sets of two objects built from the same fields are equal, so they can be one object. `share_fields_sets` gives every
object of a kept library the shared set for its shape. Nothing else about an object changes. It says the same through
`model_fields_set`, `model_dump(exclude_unset=True)` and `==`.

The shared set cannot be changed, because a change would show on every object that shares it. Its methods that change a
set raise, so an assignment to a kept object (pydantic adds the field's name to the set) is an error and never a quiet
change to 200,000 others. Nothing that reads the kept library may change it already (engine/library_cache.py). The copies
answers make get ordinary sets: `copy` and `deepcopy` of a shared set give a plain one, and that is what pydantic's
`model_copy`, `__copy__` and `__deepcopy__` give the copy.
"""

from collections.abc import Iterable

from pydantic import BaseModel


def _refused(self, *args, **kwargs):
    raise AttributeError("this set of field names is shared by every object of its shape. Copy the object (model_copy) "
                         "before changing it")


class SharedFieldsSet(set):
    """The names of the fields a group of objects were given, one object for the group. It is a real `set` because
    pydantic's serialiser insists on one, but it cannot be changed. Copies are ordinary sets."""

    __slots__ = ()
    add = discard = remove = pop = clear = update = difference_update = intersection_update = _refused
    symmetric_difference_update = __ior__ = __iand__ = __isub__ = __ixor__ = _refused

    def __copy__(self) -> set:
        return set(self)

    def __deepcopy__(self, memo=None) -> set:
        return set(self)


_SHARED: dict[frozenset, SharedFieldsSet] = {}  # a shape -> its shared set (a few dozen shapes in all)


def share_fields_set(model: BaseModel) -> None:
    """Gives `model` the shared set for its shape. An object that has it already is left as it is."""
    current = model.__pydantic_fields_set__
    if isinstance(current, SharedFieldsSet):
        return
    shape = frozenset(current)
    shared = _SHARED.get(shape)
    if shared is None:
        shared = _SHARED[shape] = SharedFieldsSet(shape)
    object.__setattr__(model, "__pydantic_fields_set__", shared)


def _models_of(thread) -> Iterable[BaseModel]:
    yield thread
    if thread.author is not None:
        yield thread.author
    if thread.whole_thread is not None:
        yield thread.whole_thread
    for comment in thread.comments:
        yield comment
        if comment.author is not None:
            yield comment.author


def _models_of_check(result) -> Iterable[BaseModel]:
    for kept in (result.kept, result.kept_notes, result.kept_agreements, result.kept_care):
        yield from kept
    for rejected in (result.rejected, result.rejected_notes, result.rejected_agreements, result.rejected_care):
        for item, _ in rejected:
            yield item


def share_thread(thread) -> None:
    """Shares the fields sets of a thread, its writer, its comments and their writers."""
    for model in _models_of(thread):
        share_fields_set(model)


def share_check(result) -> None:
    """Shares the fields sets of every mention, note, agreement and care tip of one thread's checked extraction."""
    for model in _models_of_check(result):
        share_fields_set(model)


def share_fields_sets(threads: Iterable, checked: dict) -> None:
    """Shares the fields sets of every thread (share_thread) and every checked extraction (share_check). `checked` is
    {thread id: engine.extract.CheckResult}. The kept library does it as each is read (engine/library_cache.py)."""
    for thread in threads:
        share_thread(thread)
    for result in checked.values():
        share_check(result)

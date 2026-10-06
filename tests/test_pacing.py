from backend.narration import speech_plan


def test_blank_lines_add_bounded_pauses_without_changing_words():
    text = "Book title\n\nBy Author\n\n\nIntroduction\n\n\n\nA paragraph\nwith a printed wrap."
    plan = speech_plan(text)
    assert [pause for _, pause in plan] == [0.45, 0.775, 1.1, 0.0]
    assert " ".join(part for part, _ in plan).split() == text.split()


def test_length_splits_do_not_add_paragraph_pauses():
    text = "One long continuous sentence with many words " * 30 + "\n\nNext paragraph.\n\n"
    plan = speech_plan(text, 100)
    assert sum(pause > 0 for _, pause in plan) == 1
    assert plan[-1][1] == 0
    assert all(len(part) <= 100 for part, _ in plan)

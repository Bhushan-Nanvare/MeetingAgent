from services.transcript_parser import parse_transcript

TEAMS_VTT = """WEBVTT

NOTE Recording started 2026-09-15
NOTE second line of the same note block

1
00:00:00.000 --> 00:00:04.000
<v Alice Fernandes>Let's start with the login work.</v>

2
00:00:04.200 --> 00:00:08.000
<v Alice Fernandes>Support sent six tickets this week.</v>

3
00:00:08.200 --> 00:00:12.000
<v Bob Mehta>I will add rate limiting by Wednesday.</v>
"""

ZOOM_VTT = """WEBVTT

1
00:00:01.000 --> 00:00:05.000
Carol D'Souza: The reports page is timing out.

2
00:00:05.200 --> 00:00:09.000
Dave Patil: Okay, I will look at the indexes.
"""

SRT = """1
00:00:01,000 --> 00:00:04,000
We agreed to release every Thursday.

2
00:00:04,500 --> 00:00:07,000
Eve Sharma: I will update the onboarding guide.
"""


def test_vtt_keeps_speakers_and_drops_timing():
    out = parse_transcript(TEAMS_VTT)
    assert "-->" not in out
    assert "WEBVTT" not in out
    assert "Recording started" not in out
    assert "second line of the same note block" not in out
    assert "Bob Mehta: I will add rate limiting by Wednesday." in out


def test_vtt_merges_consecutive_lines_from_same_speaker():
    out = parse_transcript(TEAMS_VTT).split("\n")
    assert out[0] == (
        "Alice Fernandes: Let's start with the login work. Support sent six tickets this week."
    )
    assert len(out) == 2


def test_zoom_style_name_prefix_is_kept():
    out = parse_transcript(ZOOM_VTT)
    assert out.startswith("Carol D'Souza: The reports page is timing out.")
    assert "Dave Patil: Okay, I will look at the indexes." in out


def test_srt_cue_numbers_are_dropped():
    out = parse_transcript(SRT)
    assert out.split("\n")[0] == "We agreed to release every Thursday."
    assert "Eve Sharma: I will update the onboarding guide." in out


def test_growing_caption_lines_are_collapsed():
    captions = """WEBVTT

00:00:01.000 --> 00:00:02.000
<v Alice>I will build</v>

00:00:02.000 --> 00:00:03.000
<v Alice>I will build the reset flow</v>
"""
    assert parse_transcript(captions) == "Alice: I will build the reset flow"


def test_plain_text_passes_through():
    text = "Alice: we ship on Thursday.\n\nBob: agreed.\n"
    assert parse_transcript(text) == "Alice: we ship on Thursday.\nBob: agreed."


def test_sentence_with_colon_is_not_read_as_a_speaker():
    vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
Here is the thing: we need indexes.
"""
    assert parse_transcript(vtt) == "Here is the thing: we need indexes."


def test_empty_input_returns_empty_string():
    assert parse_transcript("") == ""
    assert parse_transcript("WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.000\n") == ""

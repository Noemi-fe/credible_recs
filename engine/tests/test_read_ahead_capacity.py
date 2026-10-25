"""The verification budget and reading ahead's capacity (25 Oct 2026, the verify2 builder; docs/verify-bfs-2026-10-25.md,
options (b), (c) and (h)).

The review of 25 Oct measured the library (78,102 kept comments): about 2,700 pass their 30 days a day, the site read 9,600
a day against a cap of 11,520, and a week's outage would cost about 2,200 comments, ten days about 10,400. At 4,500
verification reads a day a ten-day outage loses nothing. The answers' last two tiers (the products behind the picks, and
those after them: fallbacks that are rarely shown) need a fresh check only at answer time, so they are read every 5 days
instead of every 40 hours, which frees about 1,260 reads a day. These tests keep reading ahead's capacity matched to
what then falls due, inside Reddit's limits and the visitors' reserve. Nothing here reaches the network.
"""

from engine import config

# The review's numbers: the answers the plan job would check (559 requests): 5,557 shown comments, 1,468 next in line,
# 881 behind the picks, 2,266 after those.
FIRST_TWO_TIERS = 5_557 + 1_468
LAST_TWO_TIERS = 881 + 2_266
PINGS_A_DAY = 24 * 12
# The site read 9,600 a day against a cap of 11,520 on 24 Oct 2026: it reaches 83% of what a day of pings could read.
REACHED = 9_600 / 11_520


def reads_due_a_day() -> float:
    """What falls due a day: the first two tiers every READ_AHEAD_AGAIN_HOURS, the last two every
    PLAN_FALLBACK_TIER_DAYS, and the kept comments the plan lists a day."""
    return (FIRST_TWO_TIERS * 24 / config.READ_AHEAD_AGAIN_HOURS + LAST_TWO_TIERS / config.PLAN_FALLBACK_TIER_DAYS
            + config.LIBRARY_VERIFY_READS)


def test_the_plan_asks_for_4500_kept_comments_a_day():
    assert config.LIBRARY_VERIFY_READS == 4_500


def test_the_last_two_tiers_are_read_every_5_days_the_first_two_every_40_hours():
    assert config.PLAN_FALLBACK_TIER_DAYS == 5 and config.READ_AHEAD_AGAIN_HOURS == 40
    old = (FIRST_TWO_TIERS + LAST_TWO_TIERS) * 24 / 40
    new = FIRST_TWO_TIERS * 24 / 40 + LAST_TWO_TIERS / 5
    assert round(old - new, -1) == 1_260  # the review's "about 1,260 reads a day" freed


def test_a_day_of_pings_reads_what_falls_due_with_room_to_spare():
    # 14,000 or so a day against about 9,300: even at the 83% the site reaches, a day of pings reads it all and clears a
    # backlog (after an outage) at over 2,000 a day.
    per_ping = config.READ_AHEAD_PER_PING
    assert per_ping * PINGS_A_DAY >= 1.4 * reads_due_a_day()
    assert per_ping * PINGS_A_DAY * REACHED >= 1.2 * reads_due_a_day()


def test_a_ping_reaches_its_reads_in_its_seconds_even_at_the_slowest_read_seen():
    # The live site's logs of 15 to 17 Oct 2026: in batches of 8 a ping read 24 to 32 reads in 5 s, a batch taking 1.25 to
    # 1.67 s, of which the reads' spacing (LIVE_CHECK_MIN_INTERVAL: 0.7 s for 8) was a part: a read took 0.97 s at most.
    # With reads overlapping, a ping starts min(1 / spacing, parallel / read) reads a second.
    spacing, parallel = config.LIVE_CHECK_MIN_INTERVAL, config.READ_AHEAD_PARALLEL
    slowest_read = 1.67 - (8 - 1) * spacing
    rate = min(1 / spacing, parallel / slowest_read)
    assert int(rate * config.READ_AHEAD_SECONDS) >= config.READ_AHEAD_PER_PING
    assert parallel <= config.LIVE_CHECK_PARALLEL  # no more at once than an answer reads


def test_reading_ahead_leaves_visitors_their_reserve_of_reddits_reads():
    # Reddit's embed pages answer about 200 reads in 10 minutes from one address, and the keep-warm ping comes twice in
    # that time: reading ahead takes at most 2 x READ_AHEAD_PER_PING and stops while fewer than READ_AHEAD_KEEP are left.
    # The review (option c) gives visitors 100: two fresh answers of the biggest size (an answer reads 10 to 40 comments)
    # and a margin of 20.
    assert config.READ_AHEAD_PER_PING * 2 + config.READ_AHEAD_KEEP <= 200
    assert config.READ_AHEAD_KEEP >= 100 >= 2 * 40 + 20


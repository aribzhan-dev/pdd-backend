"""Building media URLs for both ways of serving them.

The escaping differs between local and remote, and getting it backwards
produces a URL that always 404s — so both directions are pinned here.
"""
from __future__ import annotations

from app.services.media_url import build_media_url, local_url, remote_url

OTAN = "https://otan-shymkent.kz"
PDDTEST = "https://media.pddtest.kz"

# The extractor saved this clip under a name that literally contains percent
# signs; it is the case that breaks naive URL building.
ENCODED = "media/videos/situations/%D0%B1%D0%B5%D0%B7_%D0%BA%D0%B0%D1%80.mp4"
PLAIN = "media/videos/situations/q_5_95_Ev3nJNb.mp4"


def test_local_urls_escape_the_percent_signs_in_file_names() -> None:
    # Assert — on disk the file is named "%D0%B1…", so % must become %25
    assert local_url(ENCODED, "/media") == (
        "/media/media/videos/situations/%25D0%25B1%25D0%25B5%25D0%25B7_"
        "%25D0%25BA%25D0%25B0%25D1%2580.mp4"
    )


def test_remote_urls_pass_the_path_through_untouched() -> None:
    # Assert — the origin serves it at the already-encoded path
    assert remote_url(ENCODED, OTAN, PDDTEST) == f"{OTAN}/{ENCODED}"


def test_a_plain_name_is_identical_either_way_apart_from_the_host() -> None:
    # Assert
    assert local_url(PLAIN, "/media") == f"/media/{PLAIN}"
    assert remote_url(PLAIN, OTAN, PDDTEST) == f"{OTAN}/{PLAIN}"


def test_pddtest_assets_go_to_their_own_origin_without_the_prefix() -> None:
    # Arrange — the store keeps pddtest media in its own namespace
    stored = "pddtest/20251020_0510_kuk000bt9s_video.mp4"

    # Assert — the prefix is a local detail, not part of the origin's path
    assert remote_url(stored, OTAN, PDDTEST) == (
        f"{PDDTEST}/20251020_0510_kuk000bt9s_video.mp4"
    )


def test_a_trailing_slash_on_the_origin_does_not_double_up() -> None:
    # Assert
    assert remote_url(PLAIN, f"{OTAN}/", f"{PDDTEST}/") == f"{OTAN}/{PLAIN}"


def test_a_leading_slash_on_the_stored_path_is_ignored() -> None:
    # Assert
    assert remote_url(f"/{PLAIN}", OTAN, PDDTEST) == f"{OTAN}/{PLAIN}"
    assert local_url(f"/{PLAIN}", "/media") == f"/media/{PLAIN}"


def test_the_deployment_setting_chooses_between_them() -> None:
    # Act
    served_here = build_media_url(
        PLAIN,
        serve_local=True,
        prefix="/media",
        otan_origin=OTAN,
        pddtest_origin=PDDTEST,
    )
    served_remotely = build_media_url(
        PLAIN,
        serve_local=False,
        prefix="/media",
        otan_origin=OTAN,
        pddtest_origin=PDDTEST,
    )

    # Assert
    assert served_here.startswith("/media/")
    assert served_remotely.startswith(f"{OTAN}/")

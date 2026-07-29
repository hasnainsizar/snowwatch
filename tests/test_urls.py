from __future__ import annotations

from snowwatch.urls import STUB_URL_HOST, canonical_url, url_hash

ADZUNA_LANDING = (
    "https://www.adzuna.com/land/ad/5787001382?se=AgWOyKeE8RGMMPFbxp89GQ"
    "&utm_medium=api&utm_source=a1b2c3d4&v=439E69FFFD58B1604C39B22CE34E5EC40C526ABC"
)


def test_adzuna_landing_url_canonicalizes_to_ad_id():
    assert canonical_url(ADZUNA_LANDING) == "adzuna:5787001382"


def test_adzuna_volatile_tracking_params_collapse():
    other_day = ADZUNA_LANDING.replace("se=AgWOyKeE8RGMMPFbxp89GQ", "se=xHrE9C-F8RG_o5KUZcnTHw")
    assert canonical_url(other_day) == canonical_url(ADZUNA_LANDING)


def test_adzuna_details_and_landing_are_the_same_ad():
    details = "https://www.adzuna.com/details/5787001382?utm_medium=api&utm_source=a1b2c3d4"
    assert canonical_url(details) == canonical_url(ADZUNA_LANDING)


def test_distinct_adzuna_ads_stay_distinct():
    other = ADZUNA_LANDING.replace("5787001382", "5784709999")
    assert canonical_url(other) != canonical_url(ADZUNA_LANDING)


def test_adzuna_non_ad_path_falls_back_to_url_normalization():
    assert canonical_url("https://www.adzuna.com/search?q=snowflake") == (
        "https://adzuna.com/search?q=snowflake"
    )


def test_hackernews_item_id_is_preserved():
    assert canonical_url("https://news.ycombinator.com/item?id=48832208") == (
        "https://news.ycombinator.com/item?id=48832208"
    )


def test_hackernews_items_stay_distinct():
    a = canonical_url("https://news.ycombinator.com/item?id=48832208")
    b = canonical_url("https://news.ycombinator.com/item?id=48812069")
    assert a != b


def test_tracking_params_and_fragment_stripped():
    noisy = "https://news.ycombinator.com/item?id=48832208&utm_source=x&ref=y#comment-1"
    assert canonical_url(noisy) == "https://news.ycombinator.com/item?id=48832208"


def test_stackexchange_trailing_slash_and_www_normalized():
    a = canonical_url("https://stackoverflow.com/questions/79976637/delete-lineage/")
    b = canonical_url("https://www.stackoverflow.com/questions/79976637/delete-lineage")
    assert a == b


def test_query_param_order_does_not_matter():
    a = canonical_url("https://example.com/p?b=2&a=1")
    b = canonical_url("https://example.com/p?a=1&b=2")
    assert a == b


def test_case_and_whitespace_normalized():
    a = canonical_url("  HTTPS://NEWS.YCOMBINATOR.COM/ITEM?ID=48832208 ")
    b = canonical_url("https://news.ycombinator.com/item?id=48832208")
    assert a == b


def test_stub_urls_canonicalize_to_their_own_namespace():
    assert canonical_url(f"https://{STUB_URL_HOST}/postings/stub-1") == "stub:postings/stub-1"


def test_stub_urls_stay_distinct_from_each_other():
    one = canonical_url(f"https://{STUB_URL_HOST}/postings/stub-1")
    two = canonical_url(f"https://{STUB_URL_HOST}/postings/stub-2")
    assert one != two


def test_stub_canonical_key_is_stable():
    plain = canonical_url(f"https://{STUB_URL_HOST}/postings/stub-1")
    noisy = canonical_url(f"https://{STUB_URL_HOST}/postings/stub-1/?utm_source=x#frag")
    assert plain == noisy


def test_stub_key_cannot_collide_with_a_live_posting():
    # A live host serving the same path must not land on the stub's key.
    live = canonical_url("https://jobs.realboard.com/postings/stub-1")
    assert canonical_url(f"https://{STUB_URL_HOST}/postings/stub-1") != live
    assert not live.startswith("stub:")


def test_stub_and_adzuna_namespaces_are_disjoint():
    stub = canonical_url(f"https://{STUB_URL_HOST}/postings/5787001382")
    assert stub != canonical_url(ADZUNA_LANDING)
    assert stub.startswith("stub:")


def test_url_hash_follows_canonical_form():
    other_day = ADZUNA_LANDING.replace("se=AgWOyKeE8RGMMPFbxp89GQ", "se=zC-Hx_CK8RGh4YMJCQ8cOQ")
    assert url_hash(other_day) == url_hash(ADZUNA_LANDING)

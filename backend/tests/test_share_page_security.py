from routes.share import _page


def test_share_page_escapes_markup_and_script_boundaries() -> None:
    payload = '"><img src=x onerror=alert(1)>'
    page = _page(
        payload,
        payload,
        f"https://cdn.example.invalid/{payload}",
        f"https://app.example.invalid/{payload}",
    )

    assert page.count("<script>") == 1
    assert '<img src=x onerror=alert(1)>' not in page
    assert '&lt;img src=x onerror=alert(1)&gt;' in page
    assert '\\u003cimg src=x onerror=alert(1)\\u003e' in page
    assert 'href="https://app.example.invalid/&quot;&gt;&lt;img' in page

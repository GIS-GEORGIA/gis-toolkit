# -*- coding: utf-8 -*-
"""doc_search_core — თარიღის ამოღების, კატეგორიზაციისა და სორტირების ტესტები."""

from tools.doc_search_core import (
    extract_dates, latest_date, parse_category_rules, categorize, sort_results,
    SORT_MATCHES, SORT_DATE_DESC, SORT_DATE_ASC, SORT_NAME,
)


# ---- თარიღის ამოღება ----
def test_georgian_ymd():
    t = "თქვენი 2026 წლის 01 სექტემბრის №123 წერილის პასუხად"
    assert "2026-09-01" in extract_dates(t)


def test_georgian_short_form_and_cases():
    assert "2025-02-01" in extract_dates("2025 წ. 1 თებერვალს")
    assert "2024-10-15" in extract_dates("2024 წლის 15 ოქტომბერს გაიგზავნა")


def test_georgian_dmy_order():
    assert "2026-09-01" in extract_dates("01 სექტემბერი 2026")


def test_numeric_and_iso():
    assert "2026-09-01" in extract_dates("დათარიღებულია 01.09.2026")
    assert "2026-09-01" in extract_dates("2026-09-01")


def test_cadastral_code_not_a_date():
    # საკადასტრო კოდი — ბოლო ჯგუფი 4-ციფრიანი წელი არაა
    assert extract_dates("კოდი 71.63.80.094 ნაკვეთი") == []


def test_invalid_day_month_skipped():
    assert extract_dates("45.13.2026") == []       # დღე 45, თვე 13
    assert extract_dates("2026 წლის 40 სექტემბრის") == []


def test_latest_date_picks_newest():
    t = "2024 წლის 5 მარტს ... პასუხი 2026 წლის 01 სექტემბრის ... 2023-01-01"
    assert latest_date(t) == "2026-09-01"
    assert latest_date("თარიღების გარეშე ტექსტი") is None


# ---- კატეგორიზაცია ----
def test_parse_rules_and_comments():
    text = (
        "# კომენტარი\n"
        "ენერგო-პრო = ენერგო-პრო, energo-pro\n"
        "ეკონომიკა = ეკონომიკის სამინისტრო\n"
        "ცუდი ხაზი გამყოფის გარეშე\n"
    )
    rules = parse_category_rules(text)
    assert rules == [
        ("ენერგო-პრო", ("ენერგო-პრო", "energo-pro")),
        ("ეკონომიკა", ("ეკონომიკის სამინისტრო",)),
    ]


def test_categorize_first_match_wins():
    rules = parse_category_rules(
        "ენერგო-პრო = ენერგო-პრო\nეკონომიკა = ეკონომიკის სამინისტრო\n")
    assert categorize("შპს ენერგო-პრო ჯორჯია გატყობინებთ", rules) == "ენერგო-პრო"
    assert categorize("ეკონომიკის სამინისტროდან", rules) == "ეკონომიკა"
    assert categorize("სხვა ორგანიზაცია", rules) is None
    assert categorize("ტექსტი", []) is None


# ---- სორტირება ----
def _r(name, count, date):
    return {"name": name, "count": count, "doc_date": date}


def test_sort_by_matches():
    rows = [_r("b", 2, None), _r("a", 5, None), _r("c", 5, None)]
    out = [r["name"] for r in sort_results(rows, SORT_MATCHES)]
    assert out == ["a", "c", "b"]        # count desc, then name


def test_sort_date_desc_newest_first_none_last():
    rows = [_r("a", 1, "2024-01-01"), _r("b", 1, "2026-09-01"),
            _r("c", 1, None)]
    out = [r["name"] for r in sort_results(rows, SORT_DATE_DESC)]
    assert out == ["b", "a", "c"]


def test_sort_date_asc_oldest_first_none_last():
    rows = [_r("a", 1, "2024-01-01"), _r("b", 1, "2026-09-01"),
            _r("c", 1, None)]
    out = [r["name"] for r in sort_results(rows, SORT_DATE_ASC)]
    assert out == ["a", "b", "c"]


def test_sort_by_name():
    rows = [_r("Beta", 9, None), _r("alpha", 1, None)]
    out = [r["name"] for r in sort_results(rows, SORT_NAME)]
    assert out == ["alpha", "Beta"]

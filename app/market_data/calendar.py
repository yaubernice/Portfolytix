"""US equity session dates for freshness. This is not a trading calendar API."""

from __future__ import annotations

from datetime import date, timedelta


def easter_sunday(year: int) -> date:
    """Gregorian Easter. Good Friday is the preceding Friday."""
    century, year_in_century = divmod(year, 100)
    century_leap, century_remainder = divmod(century, 4)
    lunar_cycle = year % 19
    leap_correction = (century + 8) // 25
    century_correction = (century - leap_correction + 1) // 3
    lunar = (
        19 * lunar_cycle + century - century_leap - century_correction + 15
    ) % 30
    year_leap, year_remainder = divmod(year_in_century, 4)
    weekday = (
        32 + 2 * century_remainder + 2 * year_leap - lunar - year_remainder
    ) % 7
    month_offset = (lunar_cycle + 11 * lunar + 22 * weekday) // 451
    month, day_index = divmod(lunar + weekday - 7 * month_offset + 114, 31)
    return date(year, month, day_index + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        cursor = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        cursor = date(year, month + 1, 1) - timedelta(days=1)
    while cursor.weekday() != weekday:
        cursor -= timedelta(days=1)
    return cursor


def _observed(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def us_market_holidays(start_year: int, end_year: int) -> set[date]:
    """NYSE full closures. Early closes are still sessions and stay out."""
    holidays: set[date] = set()
    for year in range(start_year, end_year + 1):
        holidays.add(_observed(date(year, 1, 1)))
        holidays.add(_nth_weekday(year, 1, 0, 3))
        holidays.add(_nth_weekday(year, 2, 0, 3))
        holidays.add(easter_sunday(year) - timedelta(days=2))
        holidays.add(_last_weekday(year, 5, 0))
        if year >= 2022:
            holidays.add(_observed(date(year, 6, 19)))
        holidays.add(_observed(date(year, 7, 4)))
        holidays.add(_nth_weekday(year, 9, 0, 1))
        holidays.add(_nth_weekday(year, 11, 3, 4))
        holidays.add(_observed(date(year, 12, 25)))
    return holidays


def sessions_since(bar_day: date, today: date) -> int:
    """Weekday sessions after ``bar_day`` through ``today``, holidays excluded."""
    if today <= bar_day:
        return 0
    closed = us_market_holidays(bar_day.year, today.year)
    count = 0
    cursor = bar_day + timedelta(days=1)
    while cursor <= today:
        if cursor.weekday() < 5 and cursor not in closed:
            count += 1
        cursor += timedelta(days=1)
    return count


def bar_is_stale(latest: date, today: date, *, after_business_days: int) -> bool:
    """A weekend or a holiday gap is not, by itself, a stale bar."""
    return sessions_since(latest, today) > after_business_days

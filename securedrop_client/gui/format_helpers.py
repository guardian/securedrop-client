"""
Helper functions for formatting information in the UI

"""
import datetime
import arrow
from PyQt5.QtCore import QDateTime, QTimeZone
from dateutil import tz


def format_datetime_local(date: datetime) -> str:
    """
    Formats date as a localised string in the format e.g. Sep 16 10:15
    """
    local_timezone = str(QTimeZone.systemTimeZoneId(), encoding="utf-8")
    return arrow.get(date).to(tz.gettz(local_timezone)).format("MMM D, HH:mm")
# -*- coding: utf-8 -*-


def format_float_hour(hour_float):
    """Convert a float hour (e.g. 14.5) to HH:MM string (e.g. '14:30').

    Centralised helper used across portalGestor, portal_ap, portal_usuario
    and trabajadores to avoid four duplicated implementations.
    """
    total_minutes = int(round((hour_float or 0.0) * 60))
    hour, minute = divmod(total_minutes, 60)
    return '%02d:%02d' % (hour % 24, minute)

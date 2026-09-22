"""Inline SVG icons.

    {% load icons %}
    {% icon "map" %}
    {% icon "camera" size=20 %}

Inline rather than an icon font or sprite sheet: they inherit `currentColor`,
so a chip, a button and a sidebar link all get the right colour for free, and
there is no extra request or flash of unstyled glyphs.

The set is deliberately small and one visual family: 24x24 grid, 1.6 stroke,
round caps and joins, no fills. Adding an icon that breaks those rules will
look wrong next to the others.
"""
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Path data only; the wrapper supplies the sizing and stroke attributes.
PATHS = {
    # navigation
    "map": '<path d="M9 4 3 6.5v13L9 17l6 2.5 6-2.5v-13L15 6.5 9 4Z"/><path d="M9 4v13"/><path d="M15 6.5v13"/>',
    "pin": '<path d="M12 21s7-5.4 7-10.5A7 7 0 0 0 5 10.5C5 15.6 12 21 12 21Z"/><circle cx="12" cy="10.5" r="2.6"/>',
    "camera": '<path d="M4 8.5h2.6L8 6h8l1.4 2.5H20a1 1 0 0 1 1 1V18a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9.5a1 1 0 0 1 1-1Z"/><circle cx="12" cy="13.2" r="3.4"/>',
    "video": '<rect x="3" y="6" width="12.5" height="12" rx="2.5"/><path d="m15.5 10.5 5.5-3v9l-5.5-3"/>',
    "list": '<path d="M8.5 7h11M8.5 12h11M8.5 17h11"/><circle cx="4.6" cy="7" r="1.1"/><circle cx="4.6" cy="12" r="1.1"/><circle cx="4.6" cy="17" r="1.1"/>',
    "bell": '<path d="M18 9a6 6 0 1 0-12 0c0 5-2 6.5-2 6.5h16S18 14 18 9Z"/><path d="M13.7 19.5a2 2 0 0 1-3.4 0"/>',
    "user": '<circle cx="12" cy="8.2" r="3.7"/><path d="M4.8 20c.9-3.6 3.7-5.6 7.2-5.6s6.3 2 7.2 5.6"/>',
    "dashboard": '<rect x="3.5" y="3.5" width="7" height="8" rx="1.6"/><rect x="13.5" y="3.5" width="7" height="5" rx="1.6"/><rect x="13.5" y="10.5" width="7" height="10" rx="1.6"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.6"/>',
    # dashboard nav
    "grid": '<rect x="3.5" y="3.5" width="7.5" height="7.5" rx="1.8"/><rect x="13" y="3.5" width="7.5" height="7.5" rx="1.8"/><rect x="3.5" y="13" width="7.5" height="7.5" rx="1.8"/><rect x="13" y="13" width="7.5" height="7.5" rx="1.8"/>',
    "table": '<rect x="3.2" y="4.5" width="17.6" height="15" rx="2.2"/><path d="M3.2 9.6h17.6M9.4 9.6v9.9"/>',
    "review": '<circle cx="11" cy="11" r="6.8"/><path d="m16 16 4.2 4.2"/><path d="M8.6 11h4.8"/>',
    "check": '<path d="m4.5 12.8 4.6 4.6L19.5 7"/>',
    "chart": '<path d="M4 20V4"/><path d="M4 20h16"/><path d="m7.5 15.5 3.5-4 3 2.4 4.5-6"/>',
    "layers": '<path d="m12 3 8.5 4.6L12 12.2 3.5 7.6 12 3Z"/><path d="m3.5 12.4 8.5 4.6 8.5-4.6"/><path d="m3.5 16.9 8.5 4.6 8.5-4.6"/>',
    "users": '<circle cx="9.2" cy="8.4" r="3.4"/><path d="M2.8 19.4c.8-3.2 3.3-5 6.4-5s5.6 1.8 6.4 5"/><path d="M16.4 5.4a3.4 3.4 0 0 1 0 6.1"/><path d="M17.6 14.7c2.1.5 3.4 2 3.9 4.2"/>',
    "cog": '<circle cx="12" cy="12" r="3.1"/><path d="M19.2 14.6a1.6 1.6 0 0 0 .32 1.77l.06.06a1.9 1.9 0 1 1-2.7 2.7l-.05-.06a1.6 1.6 0 0 0-1.78-.32 1.6 1.6 0 0 0-.97 1.47v.17a1.9 1.9 0 1 1-3.8 0v-.09a1.6 1.6 0 0 0-1.05-1.47 1.6 1.6 0 0 0-1.77.32l-.06.06a1.9 1.9 0 1 1-2.7-2.7l.06-.06a1.6 1.6 0 0 0 .32-1.77 1.6 1.6 0 0 0-1.47-.97H3.3a1.9 1.9 0 1 1 0-3.8h.09a1.6 1.6 0 0 0 1.47-1.05 1.6 1.6 0 0 0-.32-1.77l-.06-.06a1.9 1.9 0 1 1 2.7-2.7l.06.06a1.6 1.6 0 0 0 1.77.32h.08A1.6 1.6 0 0 0 10.06 4V3.8a1.9 1.9 0 1 1 3.8 0v.09a1.6 1.6 0 0 0 .97 1.47 1.6 1.6 0 0 0 1.78-.32l.05-.06a1.9 1.9 0 1 1 2.7 2.7l-.06.06a1.6 1.6 0 0 0-.32 1.77v.08a1.6 1.6 0 0 0 1.47.97h.17a1.9 1.9 0 1 1 0 3.8h-.09a1.6 1.6 0 0 0-1.47.97Z"/>',
    "shield": '<path d="M12 3 5 6v5.6c0 4.4 3 7.9 7 9.4 4-1.5 7-5 7-9.4V6l-7-3Z"/><path d="m9.2 12.2 2 2 3.6-3.8"/>',
    "external": '<path d="M13.5 4.5H19a.5.5 0 0 1 .5.5v5.5"/><path d="m19.2 4.8-7.4 7.4"/><path d="M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10"/>',
    # actions / status
    "upload": '<path d="M12 16V4.8"/><path d="m7.6 9.2 4.4-4.4 4.4 4.4"/><path d="M4.5 15.5v3a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5v-3"/>',
    "download": '<path d="M12 4.8V16"/><path d="m7.6 11.6 4.4 4.4 4.4-4.4"/><path d="M4.5 15.5v3a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5v-3"/>',
    "sparkle": '<path d="m12 3.5 1.9 5.1a2 2 0 0 0 1.2 1.2l5.1 1.9-5.1 1.9a2 2 0 0 0-1.2 1.2L12 20l-1.9-5.2a2 2 0 0 0-1.2-1.2L3.8 11.7l5.1-1.9a2 2 0 0 0 1.2-1.2L12 3.5Z"/><path d="M5.2 4v2.6M3.9 5.3h2.6"/>',
    "brain": '<path d="M9.5 5.2A2.8 2.8 0 0 0 5 7.3a2.6 2.6 0 0 0-1.4 4.1A2.9 2.9 0 0 0 5 16a2.8 2.8 0 0 0 4.5 2.3Z"/><path d="M14.5 5.2A2.8 2.8 0 0 1 19 7.3a2.6 2.6 0 0 1 1.4 4.1A2.9 2.9 0 0 1 19 16a2.8 2.8 0 0 1-4.5 2.3Z"/><path d="M12 5v14"/>',
    "wrench": '<path d="M15.6 7.4a3.9 3.9 0 0 0 4.8 4.8l-8 8a2.4 2.4 0 0 1-3.4-3.4l8-8Z"/><path d="M19.6 4.4 17 7"/>',
    "locate": '<circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="7.5"/><path d="M12 2v2.2M12 19.8V22M22 12h-2.2M4.2 12H2"/>',
    "search": '<circle cx="11" cy="11" r="6.6"/><path d="m16 16 4.5 4.5"/>',
    "close": '<path d="m6 6 12 12M18 6 6 18"/>',
    "arrow-right": '<path d="M4.8 12h14"/><path d="m13.2 6.2 5.8 5.8-5.8 5.8"/>',
    "empty": '<ellipse cx="12" cy="14.5" rx="7.5" ry="4.2"/><path d="M6 12.5c1.2-2 3.4-3 6-3"/>',
}

WRAPPER = (
    '<svg class="ico {cls}" width="{size}" height="{size}" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="{stroke}" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" '
    'focusable="false">{paths}</svg>'
)


@register.simple_tag
def icon(name, size=18, stroke=1.6, cls=""):
    paths = PATHS.get(name)
    if paths is None:
        # Loud in development, harmless in production: an empty box is easier
        # to spot than a silently missing icon.
        paths = '<rect x="4" y="4" width="16" height="16" rx="3"/>'
    return mark_safe(
        WRAPPER.format(paths=paths, size=size, stroke=stroke, cls=cls)
    )

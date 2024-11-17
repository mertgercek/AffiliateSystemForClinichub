from flask import Flask
from markupsafe import Markup, escape

def nl2br(value):
    """Convert newlines to HTML line breaks."""
    if not value:
        return ''
    return Markup(escape(value).replace('\n', '<br>\n'))

def flag(country_code):
    """Convert country code to flag emoji."""
    if not country_code:
        return ''
    # Convert country code to regional indicator symbols
    # Each letter is converted to a regional indicator symbol by adding 127397 to its Unicode value
    return ''.join(chr(ord(c.upper()) + 127397) for c in country_code) 
"""Implement markdown rendering for templates.
"""

import markdown
from django import template
from django.template.defaultfilters import stringfilter

register = template.Library()


@register.filter
@stringfilter
def convert_markdown(value):
    """Implements a filter that renders markdown into html. Useful for
    Jinja2 templates.
    """
    html = markdown.markdown(
        value,
        extensions=["markdown.extensions.fenced_code", "markdown.extensions.tables"],
    )
    return html

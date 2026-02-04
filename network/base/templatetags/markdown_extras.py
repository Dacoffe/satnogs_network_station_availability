"""Implement markdown rendering for templates.
"""

import markdown
import nh3
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
    # Pylint false positive below, see https://github.com/pylint-dev/pylint/issues/8756
    return nh3.clean(   # pylint: disable=no-member
        html=html,
        tags={
            "p",
            "b",
            "i",
            "u",
            "em",
            "strong",
            "ul",
            "ol",
            "li",
            "a",
            "table",
            "thead",
            "tbody",
            "tr",
            "th",
            "td",
            "blockquote",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
        },
        attributes={
            "a": {"href", "title"},
            "th": {"colspan", "rowspan"},
            "td": {"colspan", "rowspan"},
        },
        url_schemes={"http", "https", "mailto"}
    )

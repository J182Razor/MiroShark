"""Protect the scenario selector's three supported application modes."""
from html.parser import HTMLParser
from pathlib import Path


class ModeOptions(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_mode = False
        self.values = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'select':
            self.in_mode = attributes.get('id') == 'mode'
        elif tag == 'option' and self.in_mode:
            self.values.append(attributes.get('value'))

    def handle_endtag(self, tag):
        if tag == 'select':
            self.in_mode = False


def test_scenario_selector_exposes_all_supported_modes():
    parser = ModeOptions()
    page = Path(__file__).resolve().parents[1] / 'static' / 'index.html'
    parser.feed(page.read_text(encoding='utf-8'))
    assert parser.values == ['none', 'new', 'existing']

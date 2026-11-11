import unittest
from html.parser import HTMLParser
from amigo.markdown import render


class Tags(HTMLParser):
    def __init__(self, text):
        super().__init__(); self.tags = []; self.attrs = []; self.feed(text)
    def handle_starttag(self, tag, attrs): self.tags.append(tag); self.attrs.extend(attrs)


class MarkdownTests(unittest.TestCase):
    def test_prose_and_lists(self):
        blocks = render('# Título\n\n**ação** *café* ~~antes~~ `a < b & c`\n\n3. primeiro\n   - sub\n\n   outro parágrafo\n\n---')
        self.assertEqual(blocks[0]['level'], 1)
        self.assertIn('<b>ação</b>', blocks[1]['html'])
        self.assertIn('<i>café</i>', blocks[1]['html'])
        self.assertIn('<s>antes</s>', blocks[1]['html'])
        self.assertIn('<code>a &lt; b &amp; c</code>', blocks[1]['html'])
        self.assertEqual([(b['marker'], b['indent']) for b in blocks[2:5]], [('3.', 1), ('•', 2), ('', 1)])
        self.assertEqual(blocks[-1]['kind'], 'rule')

    def test_quotes_and_literal_code(self):
        blocks = render('> café\n>\n> > informação\n\n```python\na < b > c & "ação"\n<img src="https://example.com/x">\n```')
        self.assertEqual([b['quote'] for b in blocks], [1, 2, 0])
        self.assertEqual(blocks[-1]['language'], 'python')
        self.assertEqual(blocks[-1]['code'], 'a < b > c & "ação"\n<img src="https://example.com/x">\n')

    def test_no_resource_markup(self):
        blocks = render('<img src="file:///etc/passwd">\n\n![alt](https://example.com/a.png) ![ref][i]\n\n[i]: https://example.com/b.png\n\n[local](file:///tmp/a) [bad](javascript:alert) [web](https://example.com/?a=1&b=2) <https://example.com>')
        for block in blocks:
            tags = Tags(block.get('html', ''))
            self.assertNotIn('img', tags.tags)
            self.assertNotIn('script', tags.tags)
            self.assertTrue(all(key == 'href' and value.startswith('https://') for key, value in tags.attrs))
        self.assertIn('&lt;img', blocks[0]['html'])
        self.assertIn('[imagem: alt]', blocks[1]['html'])
        self.assertIn('[imagem: ref]', blocks[1]['html'])

    def test_tables(self):
        table = render('| A | B |\n| :-- | --: |\n| ação | **café** |')[0]
        self.assertEqual(table['kind'], 'table')
        self.assertEqual(table['aligns'], ['left', 'right'])
        self.assertTrue(table['rows'][0]['header'])
        self.assertFalse(table['rows'][1]['header'])
        self.assertEqual(table['rows'][1]['cells'], ['ação', '<b>café</b>'])

    def test_every_stream_prefix(self):
        text = '# Ação\n\n> Nota com **ênfase**\n\n```python\nx = "< & >"\n```\n\n| A | B |\n| - | - |\n| café | olá |'
        for length in range(len(text) + 1):
            blocks = render(text[:length])
            self.assertEqual([b['id'] for b in blocks], list(map(str, range(len(blocks)))))
        self.assertEqual(render(text)[2]['code'], 'x = "< & >"\n')

    def test_code_normalizes_commonmark_line_endings_only(self):
        # Token content excludes fences, retains trailing newlines and entities.
        self.assertEqual(render('```unknown\n&lt; & >\n\n```')[0]['code'], '&lt; & >\n\n')

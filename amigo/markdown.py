"""Passive Markdown presentation. No renderer-supplied HTML or resource URLs.

Only this module generates the small rich-text subset consumed by Qt. The
original Markdown remains the database/API/copy format; blocks are disposable.
"""
from html import escape
from urllib.parse import urlsplit
from markdown_it import MarkdownIt


def inline(tokens):
    parts = []
    links = []
    for token in tokens or []:
        kind = token.type
        if kind == 'text': parts.append(escape(token.content))
        elif kind == 'code_inline': parts.append('<code>' + escape(token.content) + '</code>')
        elif kind in ('softbreak', 'hardbreak'): parts.append('<br>')
        elif kind == 'image': parts.append(escape('[imagem: ' + token.content + ']'))
        elif kind == 'link_open':
            href = token.attrGet('href') or ''
            try: allowed = urlsplit(href).scheme.lower() in ('https', 'http') and bool(urlsplit(href).hostname)
            except ValueError: allowed = False
            links.append(allowed)
            if allowed: parts.append('<a href="' + escape(href, quote=True) + '">')
        elif kind == 'link_close':
            if links and links.pop(): parts.append('</a>')
        elif kind in ('strong_open', 'strong_close', 'em_open', 'em_close', 's_open', 's_close'):
            tag = {'strong': 'b', 'em': 'i', 's': 's'}[kind.rsplit('_', 1)[0]]
            parts.append('<' + ('/' if kind.endswith('_close') else '') + tag + '>')
        else: parts.append(escape(token.content))
    return ''.join(parts)


def render(markdown):
    # A parser per job avoids sharing mutable parser state across worker threads.
    parser = MarkdownIt('js-default', {'html': False, 'linkify': False})
    tokens = parser.parse(markdown)
    blocks, lists, items = [], [], []
    quote = 0
    i = 0

    def add(kind, **values):
        marker = ''
        if items and items[-1]['pending']:
            marker = items[-1]['marker']; items[-1]['pending'] = False
        blocks.append(dict(id=str(len(blocks)), kind=kind, indent=len(items), quote=quote,
                           marker=marker, **values))

    while i < len(tokens):
        token = tokens[i]; kind = token.type
        if kind == 'blockquote_open': quote += 1
        elif kind == 'blockquote_close': quote -= 1
        elif kind in ('bullet_list_open', 'ordered_list_open'):
            lists.append({'ordered': kind == 'ordered_list_open', 'next': int(token.attrGet('start') or 1)})
        elif kind in ('bullet_list_close', 'ordered_list_close'): lists.pop()
        elif kind == 'list_item_open':
            entry = lists[-1]; items.append({'pending': True, 'marker': str(entry['next']) + '.' if entry['ordered'] else '•'})
            entry['next'] += 1
        elif kind == 'list_item_close': items.pop()
        elif kind in ('paragraph_open', 'heading_open'):
            body = tokens[i + 1]
            add('text', html=inline(body.children), level=int(token.tag[1:]) if kind == 'heading_open' else 0)
            i += 2
        elif kind in ('fence', 'code_block'):
            add('code', code=token.content, language=token.info.strip().split(maxsplit=1)[0] if token.info.strip() else '')
        elif kind == 'hr': add('rule')
        elif kind == 'table_open':
            rows, row, aligns, widths = [], [], [], []
            header = False
            i += 1
            while tokens[i].type != 'table_close':
                cell = tokens[i]
                if cell.type == 'thead_open': header = True
                elif cell.type == 'thead_close': header = False
                elif cell.type == 'tr_open': row = []
                elif cell.type == 'tr_close': rows.append({'header': header, 'cells': row})
                elif cell.type in ('th_open', 'td_open'):
                    body = tokens[i + 1]; column = len(row)
                    style = cell.attrGet('style') or ''
                    align = 'right' if 'right' in style else 'center' if 'center' in style else 'left'
                    # Plain character hints only affect column sizing, not markup.
                    length = len(body.content)
                    if column >= len(widths): widths.append(length); aligns.append(align)
                    else: widths[column] = max(widths[column], length)
                    row.append(inline(body.children)); i += 2
                i += 1
            add('table', rows=rows, aligns=aligns, widths=widths)
        i += 1
    return blocks

"""Synthetic parser/cache benchmark; never reads user conversations."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtTest import QTest
from amigo.markdown import render
from amigo.render_cache import Presentation

app=QCoreApplication([])
text=('## Ação\n\nUm parágrafo com **negrito**, café e informação.\n\n'
      '```python\nprint("< & >")\n```\n\n| A | B |\n| - | - |\n| um | dois |\n\n')*150
started=time.perf_counter();blocks=render(text);parse_ms=(time.perf_counter()-started)*1000
cache=Presentation();started=time.perf_counter();cache.get(1,text);request_ms=(time.perf_counter()-started)*1000
while cache.worker or cache.pending:QTest.qWait(5)
started=time.perf_counter()
for _ in range(100):cache.get(1,text)
reuse_ms=(time.perf_counter()-started)*10
cache.close()
print(json.dumps({'bytes':len(text.encode()),'blocks':len(blocks),'parser_ms':round(parse_ms,2),'async_request_ms':round(request_ms,2),'cached_request_mean_ms':round(reuse_ms,3)}))

"""Native visual/streaming assertions against synthetic messages only."""
import json
import time
from PyQt6.QtCore import QObject, QMetaObject, Qt, QCoreApplication, QPoint, QPointF
from PyQt6.QtGui import QGuiApplication, QWheelEvent
from PyQt6.QtTest import QTest

SAMPLE = '''## Uma resposta mais legível

Texto em **português**, com *ênfase*, ~~rasurado~~ e `código em linha`.
Uma ligação para [a documentação do KDE](https://develop.kde.org).

> Uma citação com margem e barra lateral.
>
> - Primeiro ponto
>   - Um detalhe dentro da lista

```python
# Símbolos preservados: < > &
for café in ["ação", "informação"]:
    print(café, "< & >")
```

| Opção | Descrição | Valor |
| :-- | :-- | --: |
| A | Texto ajustado à largura disponível, mesmo quando a célula tem uma explicação mais longa. | 12 |
| B | **Outra** possibilidade | 24 |

---

<img src="https://example.invalid/never-load.png"> ![sem acesso à rede](https://example.invalid/image.png)
'''


def visual_find(root, name):
    found=[]
    def visit(item):
        if item.objectName()==name:found.append(item)
        for child in item.childItems():visit(child)
    visit(root.contentItem())
    return found


def verify_markdown(controller, root, popup, capture):
    controller.newConversation()
    controller.history.add(controller.conversation, 'user', 'Demonstração de Markdown')
    mid = controller.history.add(controller.conversation, 'assistant', SAMPLE, status='streaming')
    controller.reload()
    def wait_render():
        deadline=time.monotonic()+4
        while time.monotonic()<deadline:
            state=json.loads(controller.stateJson)
            if not controller.presentation.pending and not controller.presentation.worker:break
            QTest.qWait(30)
        QTest.qWait(150)
        assert state['messages'][-1]['blocks']
    wait_render()
    capture(popup,'markdown-initial')
    code=next(iter(visual_find(popup,'markdownCode')),None);button=next(iter(visual_find(popup,'copyCode')),None)
    assert code and button, 'Code component missing'
    expected='# Símbolos preservados: < > &\nfor café in ["ação", "informação"]:\n    print(café, "< & >")\n'
    assert code.property('text')==expected
    QMetaObject.invokeMethod(button,'clicked')
    assert QGuiApplication.clipboard().text()==expected
    controller.copy(json.loads(controller.stateJson)['messages'][-1]['raw'])
    assert QGuiApplication.clipboard().text()==SAMPLE
    # Verify tables have real, positive geometry, and long lines scroll locally.
    cells=visual_find(popup,'markdownCell')
    assert len(cells)==9 and all(c.property('height')>0 for c in cells)
    scroll=root.findChild(QObject,'answerScroll')
    assert abs(scroll.property('contentY'))<2, 'Initial response jumped to bottom'
    scroll.setProperty('contentY',0);QTest.qWait(30)
    capture(popup,'markdown-top')
    scroll.setProperty('contentY',300);QTest.qWait(30);capture(popup,'markdown-code')
    scroll.setProperty('contentY',scroll.property('contentHeight')-scroll.property('height'));QTest.qWait(30);capture(popup,'markdown-table')
    scroll.setProperty('contentY',100);before=scroll.property('contentY')
    # Stable message/block objects while only the last paragraph streams.
    for suffix in ('\n\nTexto **incom', 'pleto**.\n\n' + 'Outra frase. '*100):
        controller.history.db.execute('UPDATE messages SET content=content||? WHERE id=?',(suffix,mid))
        controller.history.db.commit();controller.reload();wait_render()
        assert visual_find(popup,'markdownCode')[0] is code, 'Streaming recreated existing code'
        assert abs(scroll.property('contentY')-before)<2, 'Reading position moved'
    jump=root.findChild(QObject,'amigoScrollToEnd')
    assert jump.property('visible')
    QMetaObject.invokeMethod(jump,'clicked');QTest.qWait(30)
    assert abs(scroll.property('contentY')-max(0,scroll.property('contentHeight')-scroll.property('height')))<2
    bottom_before=scroll.property('contentY')
    # An explicit jump is one-shot, not an opt-in to automatic following.
    controller.history.db.execute('UPDATE messages SET content=content||? WHERE id=?',('\n\nFim. '*150,mid))
    controller.history.db.commit();controller.reload();wait_render()
    assert abs(scroll.property('contentY')-bottom_before)<2, 'Streaming followed after manual jump'
    assert scroll.property('contentHeight')-scroll.property('height')>bottom_before+40
    # Completion/metadata updates must also leave a manually chosen position alone.
    scroll.setProperty('contentY',80)
    controller.history.db.execute("UPDATE messages SET status='complete' WHERE id=?",(mid,))
    controller.history.db.commit();controller.reload();wait_render()
    assert abs(scroll.property('contentY')-80)<2, 'Completed response snapped back'
    position=scroll.mapToScene(QPointF(scroll.width()/2,min(100,scroll.height()/2)))
    wheel=QWheelEvent(position,popup.mapToGlobal(position),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
    QCoreApplication.sendEvent(popup,wheel);QTest.qWait(200)
    after_wheel=scroll.property('contentY')
    assert 0<=after_wheel<80, 'Mouse wheel did not scroll the completed answer'
    controller.changed.emit();QTest.qWait(100)
    assert abs(scroll.property('contentY')-after_wheel)<2, 'Metadata snapped the scrolled answer back'
    scroll.setProperty('contentY',100)
    controller.history.add(controller.conversation,'user','Outra pergunta')
    controller.history.add(controller.conversation,'assistant','Nova resposta. '*80)
    controller.reload();wait_render()
    assert abs(scroll.property('contentY')-100)<2, 'Next exchange jumped to bottom'
    # Return to the original message for the independent theme/width checks.
    controller.history.db.execute('DELETE FROM messages WHERE conversation=? AND id>?',(controller.conversation,mid))
    controller.history.db.commit();controller.reload();wait_render()
    code=visual_find(popup,'markdownCode')[0]
    # A live theme change must update highlighting without rebuilding the block.
    from PyQt6.QtQml import QQmlEngine, QQmlExpression
    def evaluate(script):
        expression=QQmlExpression(QQmlEngine.contextForObject(code),code,script)
        value=expression.evaluate()
        assert not expression.hasError(),expression.error().toString()
        return value
    evaluate('root.Kirigami.Theme.inherit = false; root.Kirigami.Theme.backgroundColor = "#fafafa"; root.Kirigami.Theme.textColor = "#202020"')
    QTest.qWait(30)
    light=evaluate('highlighter.theme.name')
    evaluate('root.Kirigami.Theme.backgroundColor = "#202020"; root.Kirigami.Theme.textColor = "#fafafa"')
    QTest.qWait(30)
    dark=evaluate('highlighter.theme.name')
    assert light!=dark, ('Highlighter ignored live theme change',str(light),str(dark))
    evaluate('root.Kirigami.Theme.inherit = true')
    # Narrow viewport plus a wide table and a long code line.
    extended=SAMPLE+'\n```unknown-language\n'+'a < b & café; '*100+'\n```\n\n| A | B | C | D | E | F |\n| - | - | - | - | - | - |\n| 1 | 2 | 3 | 4 | 5 | 6 |'
    controller.history.db.execute('UPDATE messages SET content=? WHERE id=?',(extended,mid));controller.history.db.commit();controller.reload();wait_render()
    assert len(visual_find(popup,'markdownCode'))==2
    assert len(visual_find(popup,'markdownCell'))==21
    from PyQt6.QtCore import QRectF
    old_area=root.property('available');root.setProperty('available',QRectF(0,30,480,870));QTest.qWait(150)
    scroll.setProperty('contentY',max(0,scroll.property('contentHeight')-scroll.property('height')));QTest.qWait(50);capture(popup,'markdown-narrow')
    assert scroll.property('contentWidth')<=scroll.property('width')+1
    assert scroll.property('width')<450
    root.setProperty('available',old_area);QTest.qWait(50)
    return ['native Markdown blocks','exact code and response copy','positive table geometry','stable streaming delegates','reading position retained','manual scrolling only','live theme change','narrow viewport']

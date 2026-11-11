import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.plasma.components as PC
import org.kde.kirigami as Kirigami

Item {
    id: view
    required property var bridge
    property var state: JSON.parse(bridge.stateJson)
    property bool historyOpen: false
    property var historyRows: []
    property bool historyHasMore: false
    property string deleteId: ""
    property string displayedConversation: ""
    ListModel { id: messageModel }
    function syncMessages() {
        if (messageModel.count > state.messages.length || (messageModel.count && state.messages.length && messageModel.get(0).messageId !== state.messages[0].id)) messageModel.clear();
        for (let i = 0; i < state.messages.length; ++i) {
            const row = state.messages[i];
            const item = {messageId: row.id, messageRole: row.role, markdown: row.content, rawText: row.raw, messageStatus: row.status, presentation: JSON.stringify(row.blocks || (row.raw ? [{id:"0", kind:"plain", text:row.raw, indent:0, quote:0, marker:""}] : []))};
            if (i >= messageModel.count) messageModel.append(item); else {
                const old = messageModel.get(i);
                for (const key in item) if (old[key] !== item[key]) messageModel.setProperty(i, key, item[key]);
            }
        }
    }
    Component.onCompleted: { syncMessages(); prompt.text = state.draft; displayedConversation = state.conversation; }
    signal hideRequested()
    function focusComposer() { if (state.ready) prompt.forceActiveFocus(); else key.forceActiveFocus(); }
    function saveDraft() { draftTimer.stop(); bridge.setDraft(prompt.text); }
    function submit() {
        if (state.busy || !prompt.text.trim()) return;
        draftTimer.stop();
        bridge.send(prompt.text, think.checked);
        prompt.text = "";
        focusComposer();
    }
    function toggleHistory() {
        historyOpen = !historyOpen;
        if (historyOpen) { refreshHistory(); Qt.callLater(() => historySearch.forceActiveFocus()); }
        else focusComposer();
    }
    function taskDetails() {
        const task = state.task;
        if (!task) return "";
        const details = [];
        if (task.providers && task.providers.length) details.push(task.providers.join(" · "));
        if (task.elapsed) details.push(Number(task.elapsed).toFixed(1) + " s");
        if (task.unknown_cost_rounds) {
            details.push(task.known_cost > 0 ? "$" + Number(task.known_cost).toFixed(6) + " + ?" : "Custo indisponível");
        } else if (!state.busy || task.known_cost > 0) {
            details.push("$" + Number(task.known_cost).toFixed(6) + (state.busy ? " parcial" : ""));
        }
        return details.join("  ·  ");
    }
    function refreshHistory() { bridge.requestHistory(historySearch.text, 0); }
    Connections {
        target: bridge
        function onHistoryReady(text, append) { const rows = JSON.parse(text); view.historyRows = append ? view.historyRows.concat(rows) : rows; view.historyHasMore = rows.length === 30; }
        function onChanged() {
            const oldId = view.displayedConversation;
            view.state = JSON.parse(bridge.stateJson);
            view.syncMessages();
            if (oldId !== view.state.conversation) {
                draftTimer.stop();
                view.historyOpen = false;
                prompt.text = view.state.draft;
            }
            view.displayedConversation = view.state.conversation;
        }
    }
    Keys.onEscapePressed: { if (historyOpen) historyOpen = false; else hideRequested(); }
    Shortcut { sequence: "Ctrl+N"; enabled: view.visible; onActivated: { saveDraft(); bridge.newConversation(); focusComposer(); } }
    Timer { id: draftTimer; interval: 350; onTriggered: bridge.setDraft(prompt.text) }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing
        spacing: Kirigami.Units.smallSpacing
        RowLayout {
            visible: view.state.ready
            Kirigami.Heading { text: "O Amigo"; level: 3; Layout.fillWidth: true }
            PC.ToolButton { visible: !!view.state.browserEnabled; icon.name: "internet-web-browser"; text: "Ver browser"; display: QQC2.AbstractButton.IconOnly; onClicked: bridge.showBrowser(); QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered }
            PC.ToolButton { icon.name: "document-new"; text: "Nova conversa"; display: QQC2.AbstractButton.IconOnly; enabled: !view.state.busy; onClicked: { view.saveDraft(); bridge.newConversation(); view.focusComposer(); } QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered }
            PC.ToolButton { icon.name: "view-history"; text: "Histórico"; display: QQC2.AbstractButton.IconOnly; checked: view.historyOpen; checkable: true; onClicked: view.toggleHistory(); QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered }
            PC.ToolButton { icon.name: "window-pin"; text: "Fixar popup"; display: QQC2.AbstractButton.IconOnly; checkable: true; checked: view.state.pinned; onClicked: bridge.setPinned(checked); QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered }
            PC.ToolButton { icon.name: "configure"; text: "Definições"; display: QQC2.AbstractButton.IconOnly; onClicked: bridge.openSettings(); QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered }
        }
        StackLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            currentIndex: !view.state.ready ? 0 : view.historyOpen ? 1 : 2
            Item {
                ColumnLayout {
                    anchors.centerIn: parent; width: Math.min(parent.width - 48, 460); spacing: Kirigami.Units.largeSpacing
                    Kirigami.Heading { text: "O Amigo"; level: 1; Layout.alignment: Qt.AlignHCenter }
                    PC.TextField { id: key; visible: !bridge.externalClient; Layout.fillWidth: true; echoMode: TextInput.Password; placeholderText: "Chave do OpenRouter"; Accessible.description: "Guardada no KWallet deste computador"; enabled: !view.state.keyBusy; onAccepted: { bridge.saveKey(text); text = ""; } }
                    PC.Button { visible: !bridge.externalClient; text: view.state.keyBusy ? "A testar…" : "Guardar e testar"; icon.name: "wallet-open"; enabled: !view.state.keyBusy && key.text.length > 0; Layout.alignment: Qt.AlignHCenter; onClicked: { bridge.saveKey(key.text); key.text = ""; } }
                    PC.Button { visible: !bridge.externalClient; text: "Testar chave já guardada"; flat: true; enabled: !view.state.keyBusy; Layout.alignment: Qt.AlignHCenter; onClicked: bridge.testKey() }
                    PC.Button { visible: bridge.externalClient; text: "Configurar conta no O Amigo"; icon.name: "configure"; Layout.alignment: Qt.AlignHCenter; onClicked: bridge.openSettings() }
                    PC.Label { text: view.state.notice; wrapMode: Text.WordWrap; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter }
                }
            }
            ColumnLayout {
                RowLayout {
                    PC.TextField { id: historySearch; Layout.fillWidth: true; placeholderText: "Pesquisar conversas…"; onTextEdited: searchTimer.restart() }
                    PC.ToolButton { text: "Voltar"; icon.name: "go-previous"; display: QQC2.AbstractButton.IconOnly; onClicked: view.toggleHistory(); QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered }
                }
                Timer { id: searchTimer; interval: 250; onTriggered: view.refreshHistory() }
                ListView {
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; model: view.historyRows
                    delegate: QQC2.ItemDelegate {
                        required property var modelData
                        width: ListView.view.width
                        contentItem: RowLayout {
                            PC.Label { text: modelData.title; elide: Text.ElideRight; Layout.fillWidth: true }
                            PC.ToolButton { text: "Eliminar"; icon.name: "edit-delete"; display: QQC2.AbstractButton.IconOnly; onClicked: view.deleteId = modelData.id }
                        }
                        onClicked: { view.saveDraft(); bridge.selectConversation(modelData.id); view.historyOpen = false; view.focusComposer(); }
                    }
                    QQC2.ScrollBar.vertical: QQC2.ScrollBar {}
                }
                RowLayout {
                    visible: view.deleteId !== ""
                    PC.Label { text: "Eliminar esta conversa do histórico?"; Layout.fillWidth: true }
                    PC.Button { text: "Cancelar"; onClicked: view.deleteId = "" }
                    PC.Button { text: "Eliminar"; onClicked: { bridge.deleteConversation(view.deleteId); view.deleteId = ""; view.refreshHistory(); } }
                }
                PC.Button { visible: view.historyHasMore; text: "Carregar mais"; Layout.alignment: Qt.AlignHCenter; onClicked: bridge.requestHistory(historySearch.text, view.historyRows.length) }
            }
            ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: composerLayout.implicitHeight + 16
                    radius: 8
                    color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.035)
                    border.color: prompt.activeFocus ? view.Kirigami.Theme.focusColor : Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.18)
                    ColumnLayout {
                        id: composerLayout
                        x: 8; y: 8; width: parent.width - 16
                        spacing: 4
                        QQC2.ScrollView {
                            Layout.fillWidth: true; Layout.preferredHeight: Math.min(120, Math.max(44, prompt.implicitHeight))
                            QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff
                            PC.TextArea {
                                id: prompt
                                objectName: "amigoComposer"
                                placeholderText: ""
                                color: view.Kirigami.Theme.textColor
                                PC.Label {
                                    visible: !prompt.text.length && !prompt.preeditText.length
                                    x: prompt.leftPadding; y: prompt.topPadding
                                    text: "Pergunta…"; color: view.Kirigami.Theme.textColor
                                    opacity: 0.55; font: prompt.font
                                    Accessible.ignored: true
                                }
                                Accessible.name: "Mensagem"
                                wrapMode: TextEdit.Wrap; selectByMouse: true
                                background: null
                                onTextChanged: draftTimer.restart()
                                Keys.onPressed: event => {
                                    if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && !(event.modifiers & Qt.ShiftModifier)) {
                                        event.accepted = true;
                                        view.submit();
                                    } else if (event.key === Qt.Key_Escape) { event.accepted = true; view.hideRequested(); }
                                }
                            }
                        }
                        RowLayout {
                            PC.ToolButton {
                                id: think; text: "Pensar mais"; icon.name: "tools-wizard"
                                checkable: true; enabled: !view.state.busy
                                QQC2.ToolTip.text: "Ativar raciocínio mais aprofundado"
                                QQC2.ToolTip.visible: hovered
                            }
                            Item { Layout.fillWidth: true }
                            PC.Button {
                                objectName: "amigoSend"
                                text: view.state.busy ? "Interromper" : "Enviar"
                                icon.name: view.state.busy ? "process-stop" : "go-up"
                                display: QQC2.AbstractButton.IconOnly
                                enabled: view.state.busy || prompt.text.trim().length > 0
                                onClicked: { if (view.state.busy) bridge.cancel(); else view.submit(); }
                                QQC2.ToolTip.text: view.state.busy ? "Interromper" : "Enviar (Enter)"
                                QQC2.ToolTip.visible: hovered
                            }
                        }
                    }
                }
                RowLayout {
                    visible: !!view.state.task && (!!view.state.task.recovery_blocked || ["paused", "failed", "interrupted"].indexOf(view.state.task.status) >= 0)
                    PC.Button { visible: !!view.state.task && !!view.state.task.recovery_blocked; text: "Configurar recuperação"; icon.name: "configure"; onClicked: bridge.openSettings(); Layout.fillWidth: true }
                    PC.Button { text: "Continuar"; icon.name: "media-playback-start"; enabled: !view.state.busy; onClicked: bridge.resume() }
                }
                RowLayout {
                    visible: !!view.state.backgroundConversation
                    Layout.fillWidth: true
                    PC.Label { text: "Tarefa em segundo plano"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    PC.Button { text: "Ver progresso"; onClicked: { view.saveDraft(); bridge.selectConversation(view.state.backgroundConversation); } }
                }
                ColumnLayout {
                    visible: !!view.state.approval
                    Layout.fillWidth: true
                    PC.Label { text: "Confirmar operação"; font.bold: true }
                    PC.ScrollView {
                        Layout.fillWidth: true; Layout.preferredHeight: 130
                        PC.TextArea { text: view.state.approval ? view.state.approval.summary : ""; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText }
                    }
                    RowLayout {
                        PC.Button { text: "Recusar"; onClicked: bridge.decide(view.state.approval.token, false) }
                        PC.Button { text: "Autorizar esta operação"; icon.name: "dialog-ok"; onClicked: bridge.decide(view.state.approval.token, true) }
                    }
                }
                Item {
                    Layout.fillWidth: true; Layout.fillHeight: true; Layout.topMargin: Kirigami.Units.smallSpacing
                QQC2.ScrollView {
                    id: answers
                    anchors.fill: parent
                    contentWidth: availableWidth
                    QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff
                    QQC2.ScrollBar.vertical: QQC2.ScrollBar {}
                    Flickable {
                        id: answerScroll
                        objectName: "answerScroll"
                        contentWidth: width; contentHeight: answerColumn.implicitHeight
                        clip: true; boundsBehavior: Flickable.StopAtBounds
                        // Reading position belongs to the user. Stream and metadata
                        // updates must never move this viewport, even at the bottom.
                    ColumnLayout {
                        id: answerColumn
                        width: answerScroll.width; spacing: Kirigami.Units.largeSpacing
                        Repeater {
                            model: messageModel
                            ColumnLayout {
                                required property string messageRole
                                required property string markdown
                                required property string rawText
                                required property string messageStatus
                                required property string presentation
                                property var modelData: ({role: messageRole, content: markdown, raw: rawText, status: messageStatus})
                                Layout.fillWidth: true; Layout.minimumWidth: answerScroll.width; spacing: 2
                                MarkdownView {
                                    visible: messageRole === "assistant"
                                    Layout.fillWidth: true; Layout.topMargin: 4; Layout.bottomMargin: 8
                                    blocksJson: presentation
                                    onCopyRequested: text => bridge.copy(text)
                                    onLinkActivated: url => bridge.openUrl(url)
                                }
                                Rectangle {
                                    visible: messageRole !== "assistant"
                                    Layout.alignment: Qt.AlignRight
                                    Layout.preferredWidth: Math.min(answerScroll.width * 0.86, Math.max(80, userText.implicitWidth + 20))
                                    implicitHeight: userText.implicitHeight + 16
                                    radius: 8
                                    color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.06)
                                    PC.TextArea {
                                        id: userText
                                        x: 10; y: 8; width: parent.width - 20
                                        text: rawText; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                                        textFormat: TextEdit.PlainText; background: null; padding: 0
                                        Accessible.name: "A tua mensagem"
                                    }
                                }
                                RowLayout {
                                    visible: messageRole === "assistant"
                                    PC.ToolButton {
                                        visible: rawText.length > 0; icon.name: "edit-copy"; text: "Copiar resposta"
                                        display: QQC2.AbstractButton.IconOnly
                                        onClicked: bridge.copy(rawText)
                                        QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered
                                    }
                                    PC.Label { visible: ["failed", "interrupted", "paused"].indexOf(messageStatus) >= 0; text: messageStatus === "failed" ? "Resposta falhada" : messageStatus === "paused" ? "Progresso guardado" : "Resposta interrompida"; opacity: 0.65; font.pointSize: Kirigami.Theme.smallFont.pointSize }
                                    Item { Layout.fillWidth: true }
                                }
                            }
                        }
                        Repeater {
                            model: view.state.actions
                            ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                PC.ToolButton { id: actionDetails; checkable: true; text: modelData.name + " · " + (modelData.status === "complete" ? "Concluída" : modelData.status === "failed" ? "Não concluída" : modelData.status === "approval" ? "A aguardar confirmação" : "Em curso"); icon.name: modelData.status === "complete" ? "emblem-success" : modelData.status === "failed" ? "dialog-warning" : "view-refresh" }
                                PC.TextArea { visible: actionDetails.checked; text: modelData.details + "\n" + modelData.result; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText; background: null; Layout.fillWidth: true }
                            }
                        }
                        Repeater {
                            model: view.state.task ? view.state.task.sources : []
                            PC.ToolButton { required property var modelData; text: modelData.title; icon.name: "internet-web-browser"; Layout.fillWidth: true; onClicked: bridge.openUrl(modelData.url) }
                        }
                    }
                }
                }
                PC.ToolButton {
                    objectName: "amigoScrollToEnd"
                    anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 8
                    visible: answerScroll.contentY < answerScroll.contentHeight - answerScroll.height - 40
                    background: Rectangle {
                        radius: width / 2; color: Kirigami.Theme.backgroundColor
                        border.color: Qt.rgba(Kirigami.Theme.textColor.r, Kirigami.Theme.textColor.g, Kirigami.Theme.textColor.b, 0.25)
                    }
                    icon.name: "go-bottom"; text: "Ir para o fim"; display: QQC2.AbstractButton.IconOnly
                    onClicked: { answerScroll.cancelFlick(); answerScroll.contentY = Math.max(0, answerScroll.contentHeight - answerScroll.height); }
                    QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered
                }
                }
                PC.Label { visible: !!view.state.task && !!view.state.task.error; text: view.state.task ? view.state.task.error : ""; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                RowLayout {
                    objectName: "amigoTaskStatus"
                    visible: !!view.state.task
                    PC.BusyIndicator { visible: view.state.busy; running: visible; implicitWidth: 16; implicitHeight: 16 }
                    PC.Label {
                        visible: view.state.busy
                        text: view.state.approval ? "A aguardar confirmação" : view.state.task && view.state.task.status === "tool" ? "A executar…" : "A responder…"
                        opacity: 0.7; font: Kirigami.Theme.smallFont
                    }
                    Item { Layout.fillWidth: true }
                    PC.Label {
                        Layout.fillWidth: true; horizontalAlignment: Text.AlignRight
                        elide: Text.ElideLeft; opacity: 0.6; font: Kirigami.Theme.smallFont
                        text: view.taskDetails()
                        QQC2.ToolTip.text: view.taskDetails() + "\nCusto comunicado pela API; ? indica uma parte indisponível."
                        QQC2.ToolTip.visible: statusHover.hovered
                        HoverHandler { id: statusHover }
                    }
                }
            }
        }
    }
}

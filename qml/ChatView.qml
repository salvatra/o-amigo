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
    property string deleteId: ""
    ListModel { id: messageModel }
    function syncMessages() {
        if (messageModel.count > state.messages.length || (messageModel.count && state.messages.length && messageModel.get(0).messageId !== state.messages[0].id)) messageModel.clear();
        for (let i = 0; i < state.messages.length; ++i) {
            const row = state.messages[i];
            const item = {messageId: row.id, messageRole: row.role, markdown: row.content, rawText: row.raw, messageStatus: row.status};
            if (i >= messageModel.count) messageModel.append(item); else messageModel.set(i, item);
        }
    }
    Component.onCompleted: { syncMessages(); prompt.text = state.draft; }
    signal hideRequested()
    function focusComposer() { if (state.ready) prompt.forceActiveFocus(); else key.forceActiveFocus(); }
    function refreshHistory() { bridge.requestHistory(historySearch.text, 0); }
    Connections {
        target: bridge
        function onHistoryReady(text, append) { view.historyRows = append ? view.historyRows.concat(JSON.parse(text)) : JSON.parse(text); }
        function onChanged() {
            const oldId = view.state.conversation;
            view.state = JSON.parse(bridge.stateJson);
            view.syncMessages();
            if (oldId !== view.state.conversation) {
                prompt.text = view.state.draft;
            }
        }
    }
    Keys.onEscapePressed: { if (historyOpen) historyOpen = false; else hideRequested(); }
    Shortcut { sequence: "Ctrl+N"; enabled: view.visible; onActivated: { bridge.newConversation(); focusComposer(); } }
    Timer { id: draftTimer; interval: 350; onTriggered: bridge.setDraft(prompt.text) }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing
        spacing: Kirigami.Units.smallSpacing
        RowLayout {
            visible: view.state.ready
            Kirigami.Heading { text: "O Amigo"; level: 2; Layout.fillWidth: true }
            PC.ToolButton { visible: !!view.state.browserEnabled; icon.name: "internet-web-browser"; text: "Ver browser"; display: QQC2.AbstractButton.IconOnly; onClicked: bridge.showBrowser(); QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered }
            PC.ToolButton { icon.name: "document-new"; text: "Nova conversa"; display: QQC2.AbstractButton.IconOnly; enabled: !view.state.busy; onClicked: { bridge.newConversation(); view.focusComposer(); } QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered }
            PC.ToolButton { icon.name: "view-history"; text: "Histórico"; display: QQC2.AbstractButton.IconOnly; enabled: !view.state.busy; checked: view.historyOpen; checkable: true; onClicked: { view.historyOpen = !view.historyOpen; if (view.historyOpen) view.refreshHistory(); } QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered }
            PC.ToolButton { icon.name: "window-pin"; text: "Fixar popup"; display: QQC2.AbstractButton.IconOnly; checkable: true; checked: view.state.pinned; onClicked: bridge.setPinned(checked); QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered }
            PC.ToolButton { icon.name: "configure"; text: "Definições"; display: QQC2.AbstractButton.IconOnly; onClicked: bridge.openSettings(); QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered }
        }
        StackLayout {
            Layout.fillWidth: true; Layout.fillHeight: true
            currentIndex: !view.state.ready ? 0 : view.historyOpen ? 1 : 2
            Item {
                ColumnLayout {
                    anchors.centerIn: parent; width: Math.min(parent.width - 48, 460); spacing: Kirigami.Units.largeSpacing
                    Kirigami.Icon { source: "help-hint"; Layout.alignment: Qt.AlignHCenter; implicitWidth: 48; implicitHeight: 48 }
                    Kirigami.Heading { text: "Olá. Sou O Amigo."; level: 1; Layout.alignment: Qt.AlignHCenter }
                    PC.Label { text: "Cola a chave do OpenRouter para começar. Fica guardada no KWallet deste computador."; wrapMode: Text.WordWrap; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter }
                    PC.TextField { id: key; visible: !bridge.externalClient; Layout.fillWidth: true; echoMode: TextInput.Password; placeholderText: "Chave do OpenRouter"; enabled: !view.state.keyBusy; onAccepted: { bridge.saveKey(text); text = ""; } }
                    PC.Button { visible: !bridge.externalClient; text: view.state.keyBusy ? "A testar…" : "Guardar e testar"; icon.name: "wallet-open"; enabled: !view.state.keyBusy && key.text.length > 0; Layout.alignment: Qt.AlignHCenter; onClicked: { bridge.saveKey(key.text); key.text = ""; } }
                    PC.Button { visible: !bridge.externalClient; text: "Testar chave já guardada"; flat: true; enabled: !view.state.keyBusy; Layout.alignment: Qt.AlignHCenter; onClicked: bridge.testKey() }
                    PC.Button { visible: bridge.externalClient; text: "Configurar conta no O Amigo"; icon.name: "configure"; Layout.alignment: Qt.AlignHCenter; onClicked: bridge.openSettings() }
                    PC.Label { text: view.state.notice; wrapMode: Text.WordWrap; Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter }
                }
            }
            ColumnLayout {
                RowLayout {
                    PC.TextField { id: historySearch; Layout.fillWidth: true; placeholderText: "Pesquisar conversas…"; onTextEdited: searchTimer.restart() }
                    PC.Button { text: "Voltar"; onClicked: view.historyOpen = false }
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
                        onClicked: { bridge.selectConversation(modelData.id); view.historyOpen = false; view.focusComposer(); }
                    }
                    QQC2.ScrollBar.vertical: QQC2.ScrollBar {}
                }
                RowLayout {
                    visible: view.deleteId !== ""
                    PC.Label { text: "Eliminar esta conversa do histórico?"; Layout.fillWidth: true }
                    PC.Button { text: "Cancelar"; onClicked: view.deleteId = "" }
                    PC.Button { text: "Eliminar"; onClicked: { bridge.deleteConversation(view.deleteId); view.deleteId = ""; view.refreshHistory(); } }
                }
                PC.Button { text: "Carregar mais"; Layout.alignment: Qt.AlignHCenter; onClicked: bridge.requestHistory(historySearch.text, view.historyRows.length) }
            }
            ColumnLayout {
                spacing: Kirigami.Units.smallSpacing
                PC.ScrollView {
                    Layout.fillWidth: true; Layout.preferredHeight: Math.min(130, Math.max(82, prompt.implicitHeight + 4))
                    PC.TextArea {
                        id: prompt
                        objectName: "amigoComposer"
                        placeholderText: "O que queres saber ou fazer?"
                        wrapMode: TextEdit.Wrap; selectByMouse: true
                        onTextChanged: draftTimer.restart()
                        Keys.onPressed: event => {
                            if ((event.key === Qt.Key_Return || event.key === Qt.Key_Enter) && !(event.modifiers & Qt.ShiftModifier)) {
                                event.accepted = true;
                                if (!view.state.busy && text.trim()) { draftTimer.stop(); bridge.send(text, think.checked); text = ""; }
                            } else if (event.key === Qt.Key_Escape) { event.accepted = true; view.hideRequested(); }
                        }
                    }
                }
                RowLayout {
                    PC.CheckBox { id: think; text: "Pensar mais"; enabled: !view.state.busy }
                    Item { Layout.fillWidth: true }
                    PC.Button { visible: !!view.state.task && ["paused", "failed", "interrupted"].indexOf(view.state.task.status) >= 0; text: "Continuar"; icon.name: "media-playback-start"; enabled: !view.state.busy; onClicked: bridge.resume() }
                    PC.Button { visible: view.state.busy; text: "Interromper"; icon.name: "process-stop"; onClicked: bridge.cancel() }
                    PC.Button { visible: !view.state.busy; text: "Enviar"; icon.name: "mail-send"; enabled: prompt.text.trim().length > 0; onClicked: { draftTimer.stop(); bridge.send(prompt.text, think.checked); prompt.text = ""; view.focusComposer(); } }
                }
                ColumnLayout {
                    visible: !!view.state.approval
                    Layout.fillWidth: true
                    PC.Label { text: "Confirmar operação"; font.bold: true }
                    PC.ScrollView {
                        Layout.fillWidth: true; Layout.preferredHeight: 130
                        PC.TextArea { text: view.state.approval ? JSON.stringify(view.state.approval.plan, null, 2) : ""; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText }
                    }
                    RowLayout {
                        PC.Button { text: "Recusar"; onClicked: bridge.decide(view.state.approval.token, false) }
                        PC.Button { text: "Autorizar esta operação"; icon.name: "dialog-ok"; onClicked: bridge.decide(view.state.approval.token, true) }
                    }
                }
                Kirigami.Separator { Layout.fillWidth: true }
                PC.ScrollView {
                    id: answers
                    Layout.fillWidth: true; Layout.fillHeight: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: answers.availableWidth; spacing: Kirigami.Units.largeSpacing
                        PC.Label { visible: view.state.messages.length === 0; text: "Uma pergunta rápida. Ou uma ajuda no computador.\n\nEscreve em cima para começar."; opacity: 0.6; wrapMode: Text.WordWrap; Layout.fillWidth: true; Layout.topMargin: 24 }
                        Repeater {
                            model: messageModel
                            ColumnLayout {
                                required property string messageRole
                                required property string markdown
                                required property string rawText
                                required property string messageStatus
                                property var modelData: ({role: messageRole, content: markdown, raw: rawText, status: messageStatus})
                                Layout.fillWidth: true; spacing: 2
                                RowLayout {
                                    PC.Label { text: modelData.role === "user" ? "Tu" : "O Amigo"; font.bold: true; opacity: 0.7; Layout.fillWidth: true }
                                    PC.ToolButton { visible: modelData.role === "assistant" && modelData.raw.length > 0; icon.name: "edit-copy"; text: "Copiar resposta"; display: QQC2.AbstractButton.IconOnly; onClicked: bridge.copy(modelData.raw); QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered }
                                }
                                PC.TextArea { Layout.fillWidth: true; text: modelData.content; readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap; textFormat: modelData.role === "assistant" ? TextEdit.MarkdownText : TextEdit.PlainText; background: null; onLinkActivated: link => bridge.openUrl(link) }
                                PC.Label { visible: ["failed", "interrupted", "paused"].indexOf(modelData.status) >= 0; text: modelData.status === "failed" ? "Resposta falhada" : modelData.status === "paused" ? "Progresso guardado" : "Resposta interrompida"; opacity: 0.65; font.pointSize: Kirigami.Theme.smallFont.pointSize }
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
                PC.Label { visible: !!view.state.task && !!view.state.task.error; text: view.state.task ? view.state.task.error : ""; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                RowLayout {
                    PC.BusyIndicator { visible: view.state.busy; running: visible; implicitWidth: 18; implicitHeight: 18 }
                    PC.Label {
                        Layout.fillWidth: true; elide: Text.ElideRight; opacity: 0.6; font.pointSize: Kirigami.Theme.smallFont.pointSize
                        text: view.state.task ? (view.state.task.providers.join(" · ") + " · " + Number(view.state.task.elapsed || 0).toFixed(1) + " s   $" + Number(view.state.task.known_cost).toFixed(6) + (view.state.task.unknown_cost_rounds ? " conhecidos · custo restante indisponível" : " comunicado pela API")) : "OpenRouter · os ficheiros só são consultados quando pedidos"
                    }
                }
            }
        }
    }
}

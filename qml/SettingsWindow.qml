import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: window
    required property var bridge
    property var values: JSON.parse(bridge.settingsJson)
    property var categories: JSON.parse(bridge.settingsSchemaJson)
    property int category: 0
    property string feedback: ""
    property var recovery: []
    property var devices: []
    property string catalog: ""
    property bool deviceBusy: false
    Connections {
        target: bridge
        function onDevicesReady(value) { const result = JSON.parse(value); window.devices = result.devices; window.deviceBusy = false; if (result.error) window.feedback = result.error; }
        function onCatalogReady(value) { const result = JSON.parse(value); window.catalog = result.error || (result.name + "\nContexto: " + result.context_length + " tokens\nParâmetros suportados: " + (result.supported_parameters || []).join(", ")); }
    }
    visible: false
    width: 960; height: 700; minimumWidth: 720; minimumHeight: 480
    title: "Definições — O Amigo"
    objectName: "amigoSettings"
    onClosing: close => { close.accepted = false; hide(); }
    function open() { values = JSON.parse(bridge.settingsJson); recovery = JSON.parse(bridge.recoveryList()); show(); requestActivate(); }
    pageStack.initialPage: Kirigami.Page {
        title: window.categories[window.category].title
        padding: 0
        RowLayout {
            anchors.fill: parent; spacing: 0
            QQC2.ScrollView {
                Layout.preferredWidth: 210; Layout.fillHeight: true
                ColumnLayout {
                    width: 210; spacing: 2
                    Repeater {
                        model: window.categories
                        QQC2.ItemDelegate {
                            required property var modelData
                            required property int index
                            Layout.fillWidth: true
                            text: modelData.title; highlighted: window.category === index
                            onClicked: window.category = index
                        }
                    }
                }
            }
            Kirigami.Separator { Layout.fillHeight: true }
            ColumnLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.margins: Kirigami.Units.largeSpacing
                QQC2.ScrollView {
                    id: contentScroll
                    Layout.fillWidth: true; Layout.fillHeight: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: contentScroll.availableWidth; spacing: Kirigami.Units.largeSpacing
                        Repeater {
                            model: window.categories[window.category].fields
                            ColumnLayout {
                                id: field
                                required property var modelData
                                Layout.fillWidth: true; spacing: Kirigami.Units.smallSpacing
                                QQC2.Label { text: field.modelData.label; wrapMode: Text.WordWrap; Layout.fillWidth: true; visible: field.modelData.type !== "boolean" }
                                Loader {
                                    Layout.fillWidth: true
                                    sourceComponent: field.modelData.type === "boolean" ? booleanField : field.modelData.type === "choice" ? choiceField : ["multiline", "list"].indexOf(field.modelData.type) >= 0 ? multilineField : textField
                                }
                                Component {
                                    id: booleanField
                                    QQC2.CheckBox { text: field.modelData.label; checked: window.values[field.modelData.key]; onToggled: window.values[field.modelData.key] = checked }
                                }
                                Component {
                                    id: choiceField
                                    QQC2.ComboBox { model: field.modelData.choices; currentIndex: model.indexOf(window.values[field.modelData.key]); onActivated: window.values[field.modelData.key] = currentText }
                                }
                                Component {
                                    id: multilineField
                                    QQC2.ScrollView {
                                        implicitHeight: field.modelData.type === "multiline" ? 180 : 100
                                        QQC2.TextArea {
                                            text: field.modelData.type === "list" ? window.values[field.modelData.key].join("\n") : window.values[field.modelData.key]
                                            wrapMode: TextEdit.Wrap; selectByMouse: true
                                            onTextChanged: window.values[field.modelData.key] = field.modelData.type === "list" ? text.split("\n").map(line => line.trim()).filter(line => line.length > 0) : text
                                        }
                                    }
                                }
                                Component {
                                    id: textField
                                    QQC2.TextField {
                                        text: window.values[field.modelData.key] === null ? "" : String(window.values[field.modelData.key])
                                        selectByMouse: true
                                        onTextEdited: {
                                            const kind = field.modelData.type;
                                            window.values[field.modelData.key] = kind === "integer" ? Number(text) : (kind === "number" || kind === "optional_number") ? (text.trim() === "" && kind === "optional_number" ? null : Number(text)) : text;
                                        }
                                    }
                                }
                            }
                        }
                        ColumnLayout {
                            visible: window.category === 0; Layout.fillWidth: true
                            QQC2.Button { text: "Consultar capacidades deste modelo"; onClicked: { window.catalog = "A consultar…"; bridge.refreshCatalog(window.values.model); } }
                            QQC2.Label { text: window.catalog; textFormat: Text.PlainText; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        }
                        ColumnLayout {
                            visible: window.category === 3; Layout.fillWidth: true
                            Kirigami.Heading { text: "Selecionar unidades removíveis"; level: 2 }
                            QQC2.Button { text: window.deviceBusy ? "A consultar…" : "Procurar unidades ligadas"; enabled: !window.deviceBusy; onClicked: { window.deviceBusy = true; bridge.refreshDevices(); } }
                            Repeater {
                                model: window.devices
                                QQC2.CheckBox {
                                    required property var modelData
                                    text: (modelData.label || modelData.model || "Unidade") + " · " + (modelData.bytes / 1073741824).toFixed(1) + " GiB · " + modelData.filesystem
                                    checked: window.values.allowed_devices.indexOf(modelData.id) >= 0
                                    onToggled: {
                                        const chosen = window.values.allowed_devices.filter(id => id !== modelData.id);
                                        if (checked) chosen.push(modelData.id);
                                        window.values.allowed_devices = chosen;
                                    }
                                }
                            }
                            QQC2.Label { text: "A seleção só é guardada ao carregar em Aplicar. Nunca permite formatar ou alterar partições."; wrapMode: Text.WordWrap; Layout.fillWidth: true; opacity: 0.7 }
                        }
                        QQC2.Label {
                            visible: window.category === 0
                            Layout.fillWidth: true; wrapMode: Text.WordWrap; opacity: 0.7
                            text: "O modelo tem de suportar os parâmetros escolhidos. O OpenRouter recebe require_parameters e os tetos de preço em todos os pedidos. Pensar mais é ativado por conversa."
                        }
                        QQC2.Label {
                            visible: window.category === 3
                            Layout.fillWidth: true; wrapMode: Text.WordWrap; opacity: 0.7
                            text: "Credenciais, carteiras, perfis de browsers, arranque automático e o próprio assistente ficam sempre protegidos. O modelo não pode alterar estas permissões. Ações administrativas exigem revisão concreta e autenticação do sistema."
                        }
                        QQC2.GroupBox {
                            visible: window.category === 3; title: "Catálogo de ferramentas"; Layout.fillWidth: true
                            ColumnLayout {
                                width: parent.width
                                Repeater {
                                    model: JSON.parse(bridge.toolsJson)
                                    QQC2.CheckBox {
                                        required property var modelData
                                        text: modelData.name
                                        checked: window.values.disabled_tools.indexOf(modelData.name) < 0
                                        onToggled: {
                                            let disabled = window.values.disabled_tools.filter(name => name !== modelData.name);
                                            if (!checked) disabled.push(modelData.name);
                                            window.values.disabled_tools = disabled;
                                        }
                                        QQC2.ToolTip.text: modelData.description; QQC2.ToolTip.visible: hovered
                                    }
                                }
                            }
                        }
                        ColumnLayout {
                            visible: window.category === 6; Layout.fillWidth: true; spacing: Kirigami.Units.largeSpacing
                            Kirigami.Heading { text: "Conta OpenRouter"; level: 2 }
                            QQC2.Label { text: "A chave não é mostrada nem incluída na configuração ou nos diagnósticos."; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            QQC2.TextField { id: key; placeholderText: "Nova chave do OpenRouter"; echoMode: TextInput.Password; Layout.fillWidth: true }
                            RowLayout {
                                QQC2.Button { text: "Guardar e testar"; enabled: key.text.length > 0; onClicked: { bridge.saveKey(key.text); key.text = ""; } }
                                QQC2.Button { text: "Testar ligação"; onClicked: bridge.testKey() }
                                QQC2.Button { text: "Remover chave…"; onClicked: removeKeyDialog.open() }
                            }
                            QQC2.Label { text: JSON.parse(bridge.stateJson).notice; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                            Kirigami.Heading { text: "Histórico"; level: 2 }
                            QQC2.Label { text: "Podes pesquisar e eliminar conversas no popup. A exportação inclui as conversas e o registo das ações, sem a chave."; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                            QQC2.TextField { id: exportPath; placeholderText: "Caminho absoluto para um novo ficheiro .json"; Layout.fillWidth: true }
                            QQC2.Button { text: "Exportar histórico"; onClicked: window.feedback = bridge.exportHistory(exportPath.text) }
                            Kirigami.Heading { text: "Recuperação"; level: 2 }
                            QQC2.Label { text: "Operações interrompidas não são repetidas. Desfazer recusa substituir alterações posteriores feitas por ti."; Layout.fillWidth: true; wrapMode: Text.WordWrap }
                            QQC2.Button { text: "Atualizar registo"; onClicked: window.recovery = JSON.parse(bridge.recoveryList()) }
                            Repeater {
                                model: window.recovery
                                ColumnLayout {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    QQC2.Label { text: modelData.files.join("\n"); wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                                    RowLayout {
                                        QQC2.Label { text: modelData.status; opacity: 0.7; Layout.fillWidth: true }
                                        QQC2.Button { text: "Desfazer"; enabled: modelData.status === "committed"; onClicked: { window.feedback = bridge.undo(modelData.id); window.recovery = JSON.parse(bridge.recoveryList()); } }
                                    }
                                }
                            }
                            Kirigami.Heading { text: "Diagnóstico"; level: 2 }
                            QQC2.Button { text: "Copiar diagnóstico sem conversas ou segredos"; onClicked: bridge.copy(bridge.diagnostics()) }
                            QQC2.Button { text: "Sair do O Amigo"; onClicked: bridge.quit() }
                        }
                    }
                }
                QQC2.Label { text: window.feedback; visible: text.length > 0; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                RowLayout {
                    Item { Layout.fillWidth: true }
                    QQC2.Button { text: "Fechar"; onClicked: window.hide() }
                    QQC2.Button { text: "Aplicar"; icon.name: "dialog-ok-apply"; onClicked: window.feedback = bridge.saveSettings(JSON.stringify(window.values)) }
                }
            }
        }
    }
    QQC2.Dialog {
        id: removeKeyDialog
        title: "Remover a chave do KWallet?"
        standardButtons: QQC2.Dialog.Yes | QQC2.Dialog.No
        modal: true; anchors.centerIn: parent
        onAccepted: bridge.removeKey()
    }
}

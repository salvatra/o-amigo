import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PC
import org.kde.kirigami as Kirigami

Item {
    id: root
    Connections {
        target: controller
        function onSettingsRequested() { settings.show(); settings.requestActivate(); }
    }
    PlasmaCore.Dialog {
        id: popup
        visible: true
        title: "O Amigo — pré-visualização"
        location: PlasmaCore.Types.TopEdge
        type: PlasmaCore.Dialog.AppletPopup
        flags: Qt.Dialog | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint
        backgroundHints: PlasmaCore.Dialog.StandardBackground
        hideOnWindowDeactivate: !pin.checked
        mainItem: Item {
            width: 800
            height: 560
            Keys.onEscapePressed: popup.visible = false
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Kirigami.Units.largeSpacing
                spacing: Kirigami.Units.largeSpacing
                RowLayout {
                    Kirigami.Heading { text: "O Amigo"; level: 2; Layout.fillWidth: true }
                    PC.ToolButton { text: "Nova conversa"; icon.name: "document-new"; enabled: false }
                    PC.ToolButton { text: "Histórico"; icon.name: "view-history"; enabled: false }
                    PC.ToolButton { id: pin; icon.name: "window-pin"; checkable: true; text: "Fixar" }
                    PC.ToolButton { icon.name: "configure"; text: "Definições"; onClicked: controller.openSettings() }
                }
                PC.TextArea {
                    id: prompt
                    Layout.fillWidth: true
                    Layout.preferredHeight: 90
                    placeholderText: "O que queres saber ou fazer?"
                    wrapMode: TextEdit.Wrap
                }
                RowLayout {
                    PC.CheckBox { text: "Pensar mais"; enabled: false }
                    Item { Layout.fillWidth: true }
                    PC.Button { text: "Enviar"; icon.name: "mail-send"; enabled: false }
                }
                Kirigami.Separator { Layout.fillWidth: true }
                PC.ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    PC.TextArea {
                        readOnly: true
                        textFormat: TextEdit.MarkdownText
                        wrapMode: TextEdit.Wrap
                        text: "## Interface em desenvolvimento\n\nEsta pré-visualização verifica os componentes nativos e o tema. Ainda não envia pedidos nem executa ações.\n\nA instalação Quick Ask mantém-se disponível durante a migração."
                        background: null
                    }
                }
                PC.Label { text: "Pré-visualização · sem acesso à chave ou aos ficheiros pessoais"; opacity: 0.7 }
            }
        }
    }
    Kirigami.ApplicationWindow {
        id: settings
        visible: false
        width: 900; height: 640
        title: "Definições — O Amigo (pré-visualização)"
        pageStack.initialPage: Kirigami.Page {
            title: "Configuração — editor de desenvolvimento"
            ColumnLayout {
                anchors.fill: parent
                QQC2.ScrollView {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    QQC2.TextArea { id: config; text: controller.settingsJson; font.family: "monospace"; selectByMouse: true }
                }
                QQC2.Label { id: feedback }
                QQC2.Button { text: "Guardar pré-visualização"; onClicked: feedback.text = controller.saveSettings(config.text) }
            }
        }
    }
}

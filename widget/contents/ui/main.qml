import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PC
import org.kde.kirigami as Kirigami
import "shared"

PlasmoidItem {
    id: root
    toolTipMainText: "O Amigo"
    toolTipSubText: serviceBridge.connected ? "Perguntar ou pedir ajuda" : "Instala o serviço O Amigo"
    hideOnWindowDeactivate: !JSON.parse(serviceBridge.stateJson).pinned
    Bridge { id: serviceBridge }
    compactRepresentation: PC.ToolButton { icon.name: "help-hint"; text: "O Amigo"; onClicked: root.expanded = !root.expanded }
    fullRepresentation: Item {
        Layout.minimumWidth: 440; Layout.preferredWidth: 800
        Layout.minimumHeight: 360; Layout.preferredHeight: 560
        ChatView { anchors.fill: parent; visible: serviceBridge.connected; bridge: serviceBridge; onHideRequested: root.expanded = false }
        ColumnLayout {
            visible: !serviceBridge.connected; anchors.centerIn: parent; width: parent.width - 48; spacing: Kirigami.Units.largeSpacing
            Kirigami.Heading { text: "Falta o serviço O Amigo"; level: 2; Layout.alignment: Qt.AlignHCenter }
            PC.Label { text: "Este widget precisa do serviço instalado separadamente. O serviço gere a chave, o histórico e as ferramentas fora do plasmashell."; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            PC.Button { text: "Instruções de instalação"; Layout.alignment: Qt.AlignHCenter; onClicked: Qt.openUrlExternally("https://github.com/salvatra/o-amigo#installation") }
            PC.Button { text: "Voltar a tentar"; Layout.alignment: Qt.AlignHCenter; onClicked: serviceBridge.refresh() }
        }
    }
}

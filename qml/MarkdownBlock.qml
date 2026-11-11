import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.plasma.components as PC
import org.kde.kirigami as Kirigami

Item {
    id: root
    required property var block
    signal copyRequested(string text)
    signal linkActivated(string url)
    implicitHeight: loader.item ? loader.item.implicitHeight : 0
    property real inset: Math.min(width * 0.35, block.quote * 16 + block.indent * 20)
    Repeater {
        model: root.block.quote
        Rectangle { required property int index; x: index * 16; width: 2; height: root.height; radius: 1; color: Kirigami.Theme.textColor; opacity: 0.22 }
    }
    PC.Label {
        visible: root.block.marker !== ""
        text: root.block.marker; textFormat: Text.PlainText
        x: root.inset - 25; width: 21; horizontalAlignment: Text.AlignRight; topPadding: 2
    }
    Loader {
        id: loader
        x: root.inset; width: Math.max(1, root.width - x)
        sourceComponent: root.block.kind === "code" ? code : root.block.kind === "table" ? table : root.block.kind === "rule" ? rule : prose
    }
    Component {
        id: prose
        PC.TextArea {
            objectName: "markdownProse"
            text: root.block.kind === "plain" ? root.block.text : root.block.html
            textFormat: root.block.kind === "plain" ? TextEdit.PlainText : TextEdit.RichText
            readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
            background: null; padding: 0; topPadding: 2; bottomPadding: 2
            font.pointSize: Kirigami.Theme.defaultFont.pointSize * (root.block.level ? [1, 1.35, 1.22, 1.12, 1.06, 1, 1][root.block.level] : 1)
            font.bold: !!root.block.level
            color: Kirigami.Theme.textColor
            onLinkActivated: link => root.linkActivated(link)
        }
    }
    Component {
        id: code
        MarkdownCode {
            code: root.block.code; language: root.block.language
            onCopyRequested: text => root.copyRequested(text)
        }
    }
    Component {
        id: table
        MarkdownTable {
            tableData: root.block
            onLinkActivated: url => root.linkActivated(url)
        }
    }
    Component { id: rule; Kirigami.Separator { implicitHeight: 1 } }
}

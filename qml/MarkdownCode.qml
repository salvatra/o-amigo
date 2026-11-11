import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.plasma.components as PC
import org.kde.kirigami as Kirigami
import org.kde.syntaxhighlighting as Syntax

Rectangle {
    id: root
    required property string code
    required property string language
    signal copyRequested(string text)
    property color ink: Kirigami.Theme.textColor
    color: Qt.rgba(ink.r, ink.g, ink.b, 0.045)
    border.color: Qt.rgba(ink.r, ink.g, ink.b, 0.12)
    radius: 6
    implicitHeight: header.height + scroller.implicitHeight + 12
    function definition() {
        const aliases = {py:"Python", python:"Python", js:"JavaScript", javascript:"JavaScript", ts:"TypeScript", typescript:"TypeScript", sh:"Bash", bash:"Bash", shell:"Bash", console:"Bash", c:"C", cpp:"C++", "c++":"C++", json:"JSON", yaml:"YAML", yml:"YAML", html:"HTML", css:"CSS", sql:"SQL", rust:"Rust", rs:"Rust", go:"Go", java:"Java", xml:"XML", qml:"QML", md:"Markdown", markdown:"Markdown", diff:"Diff"};
        return Syntax.Repository.definitionForName(aliases[language.toLowerCase()] || language);
    }
    RowLayout {
        id: header
        x: 10; width: parent.width - 20
        PC.Label { text: root.language || "Código"; textFormat: Text.PlainText; opacity: 0.65; font: Kirigami.Theme.smallFont; Layout.fillWidth: true; elide: Text.ElideRight }
        PC.ToolButton { objectName: "copyCode"; text: "Copiar código"; icon.name: "edit-copy"; onClicked: root.copyRequested(root.code); QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered }
    }
    QQC2.ScrollView {
        id: scroller
        x: 10; y: header.height; width: parent.width - 20
        implicitHeight: editor.implicitHeight + (contentWidth > availableWidth ? 14 : 0)
        height: implicitHeight
        contentWidth: Math.max(availableWidth, editor.implicitWidth)
        contentHeight: editor.implicitHeight
        clip: true
        QQC2.ScrollBar.vertical.policy: QQC2.ScrollBar.AlwaysOff
        QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AsNeeded
        PC.TextArea {
            id: editor; objectName: "markdownCode"
            text: root.code; textFormat: TextEdit.PlainText
            readOnly: true; selectByMouse: true; wrapMode: TextEdit.NoWrap
            font.family: "monospace"; font.pointSize: Kirigami.Theme.defaultFont.pointSize * 0.95
            color: Kirigami.Theme.textColor; background: null; padding: 0
            Syntax.SyntaxHighlighter {
                id: highlighter
                textEdit: editor
                definition: root.definition()
                theme: Syntax.Repository.defaultTheme((root.Kirigami.Theme.backgroundColor.r * 0.2126 + root.Kirigami.Theme.backgroundColor.g * 0.7152 + root.Kirigami.Theme.backgroundColor.b * 0.0722) < 0.5 ? Syntax.Repository.DarkTheme : Syntax.Repository.LightTheme)
            }
        }
    }
}

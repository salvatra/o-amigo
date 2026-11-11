import QtQuick
import QtQuick.Controls as QQC2
import org.kde.plasma.components as PC
import org.kde.kirigami as Kirigami

QQC2.ScrollView {
    id: root
    required property var tableData
    signal linkActivated(string url)
    ListModel { id: tableRows }
    function syncRows() {
        while (tableRows.count > tableData.rows.length) tableRows.remove(tableRows.count - 1);
        for (let i = 0; i < tableData.rows.length; ++i) {
            const encoded = JSON.stringify(tableData.rows[i]);
            if (i >= tableRows.count) tableRows.append({encoded: encoded});
            else if (tableRows.get(i).encoded !== encoded) tableRows.setProperty(i, "encoded", encoded);
        }
    }
    onTableDataChanged: syncRows()
    Component.onCompleted: syncRows()
    property color ink: Kirigami.Theme.textColor
    property var columnWidths: {
        const desired = tableData.widths.map(n => Math.max(112, Math.min(260, n * Kirigami.Theme.defaultFont.pointSize * 0.6 + 24)));
        const total = desired.reduce((a, b) => a + b, 0);
        return desired.map(n => n + Math.max(0, availableWidth - total) / desired.length);
    }
    contentWidth: columnWidths.reduce((a, b) => a + b, 0)
    contentHeight: tableColumn.height
    implicitHeight: contentHeight + (contentWidth > availableWidth ? 14 : 0)
    clip: true
    QQC2.ScrollBar.vertical.policy: QQC2.ScrollBar.AlwaysOff
    QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AsNeeded
    Column {
        id: tableColumn
        width: root.contentWidth
        Repeater {
            model: tableRows
            Row {
                id: tableRow
                required property string encoded
                property var modelData: JSON.parse(encoded)
                property bool header: modelData.header
                property real rowHeight: {
                    let maximum = 0;
                    for (let i = 0; i < cells.count; ++i) {
                        const cell = cells.itemAt(i);
                        if (cell) maximum = Math.max(maximum, cell.contentHeight);
                    }
                    return maximum;
                }
                Repeater {
                    id: cells
                    model: tableRow.modelData.cells
                    Rectangle {
                        required property string modelData
                        required property int index
                        width: root.columnWidths[index]
                        height: tableRow.rowHeight
                        property real contentHeight: cellText.implicitHeight + 16
                        color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, tableRow.header ? 0.085 : 0.025)
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: root.ink; opacity: 0.12 }
                        PC.TextArea {
                            id: cellText; objectName: "markdownCell"
                            x: 10; y: 8; width: parent.width - 20
                            text: modelData; textFormat: TextEdit.RichText
                            readOnly: true; selectByMouse: true; wrapMode: TextEdit.Wrap
                            background: null; padding: 0; font.bold: tableRow.header
                            horizontalAlignment: root.tableData.aligns[index] === "right" ? TextEdit.AlignRight : root.tableData.aligns[index] === "center" ? TextEdit.AlignHCenter : TextEdit.AlignLeft
                            onLinkActivated: link => root.linkActivated(link)
                        }
                    }
                }
            }
        }
    }
}

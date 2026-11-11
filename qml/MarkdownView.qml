import QtQuick
import QtQuick.Layouts

Column {
    id: root
    property string blocksJson: "[]"
    signal copyRequested(string text)
    signal linkActivated(string url)
    spacing: 12
    ListModel { id: blocks }
    function sync() {
        const incoming = JSON.parse(blocksJson);
        while (blocks.count > incoming.length) blocks.remove(blocks.count - 1);
        for (let i = 0; i < incoming.length; ++i) {
            const encoded = JSON.stringify(incoming[i]);
            if (i >= blocks.count) blocks.append({encoded: encoded});
            else if (blocks.get(i).encoded !== encoded) blocks.setProperty(i, "encoded", encoded);
        }
    }
    onBlocksJsonChanged: sync()
    Component.onCompleted: sync()
    Repeater {
        model: blocks
        MarkdownBlock {
            required property string encoded
            block: JSON.parse(encoded)
            width: root.width
            onCopyRequested: text => root.copyRequested(text)
            onLinkActivated: url => root.linkActivated(url)
        }
    }
}

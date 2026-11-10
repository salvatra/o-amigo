import QtQuick
import org.kde.plasma.core as PlasmaCore

Item {
    id: root
    property var config: JSON.parse(controller.settingsJson)
    property rect available: Qt.rect(0, 30, 1440, 870)
    function place(x, y, width, height) {
        available = Qt.rect(x, y, width, height);
        popup.x = Math.round(x + (width - popup.width) / 2);
        popup.y = y + 4;
    }
    function showPopup() { popup.visible = true; popup.requestActivate(); chat.focusComposer(); }
    Connections {
        target: controller
        function onShowRequested() { root.showPopup(); }
        function onHideRequested() { popup.visible = false; }
        function onSettingsRequested() { settings.open(); }
        function onSettingsChanged() { root.config = JSON.parse(controller.settingsJson); }
        function onPlacementRequested(x, y, width, height) { root.place(x, y, width, height); }
    }
    PlasmaCore.Dialog {
        id: popup
        objectName: "amigoPopup"
        title: "O Amigo"
        visible: false
        property bool pendingPlacement: false
        location: root.config.animations ? PlasmaCore.Types.TopEdge : PlasmaCore.Types.Floating
        type: PlasmaCore.Dialog.Normal
        flags: Qt.Tool | Qt.FramelessWindowHint
        backgroundHints: PlasmaCore.Dialog.StandardBackground
        hideOnWindowDeactivate: !chat.state.pinned
        onVisibleChanged: { pendingPlacement = visible; controller.setVisible(visible); }
        onFrameSwapped: {
            if (pendingPlacement) {
                pendingPlacement = false;
                Qt.callLater(() => root.place(root.available.x, root.available.y, root.available.width, root.available.height));
            }
        }
        onWidthChanged: x = Math.round(root.available.x + (root.available.width - width) / 2)
        mainItem: ChatView {
            id: chat
            bridge: controller
            width: Math.min(root.config.width, Math.max(360, root.available.width - 32))
            height: Math.min(root.config.height, Math.max(280, root.available.height * 0.75))
            onHideRequested: popup.visible = false
        }
    }
    SettingsWindow { id: settings; bridge: controller }
}

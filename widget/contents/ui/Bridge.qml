import QtQuick
import org.kde.plasma.workspace.dbus as DBus

Item {
    id: bridge
    property bool connected: false
    readonly property bool externalClient: true
    property string stateJson: JSON.stringify({ready:false,keyBusy:false,busy:false,notice:"",conversation:"",draft:"",messages:[],pinned:false,task:null,actions:[]})
    signal changed()
    signal historyReady(string text, bool append)
    function call(method, args, callback) {
        DBus.SessionBus.asyncCall({service:"org.kde.OAmigo",path:"/OAmigo",iface:"org.kde.OAmigo",member:method,arguments:args || []},
            result => { bridge.connected = true; if (callback) callback(result.value); },
            error => { bridge.connected = false; });
    }
    function refresh() { call("Snapshot", [], value => { stateJson = value; changed(); }); }
    function send(text, thinking) { call("Send",[text,thinking]); }
    function newConversation() { call("NewConversation"); }
    function cancel() { call("Cancel"); }
    function resume() { call("Continue"); }
    function setDraft(text) { call("SetDraft",[text]); }
    function setPinned(value) { call("SetPinned",[value]); }
    function selectConversation(id) { call("SelectConversation",[id]); }
    function deleteConversation(id) { call("DeleteConversation",[id]); }
    function copy(text) { call("Copy",[text]); }
    function openSettings() { call("Settings"); }
    function openUrl(url) { if (/^https?:\/\//i.test(url)) Qt.openUrlExternally(url); }
    function requestHistory(query, offset) { call("History",[query,new DBus.int32(offset)],value => historyReady(value,offset>0)); }
    function saveKey(ignored) { openSettings(); }
    function testKey() { openSettings(); }
    DBus.DBusServiceWatcher {
        busType: DBus.BusType.Session; watchedService: "org.kde.OAmigo"
        onRegisteredChanged: { bridge.connected = registered; if (registered) bridge.refresh(); }
    }
    DBus.SignalWatcher {
        busType: DBus.BusType.Session; service: "org.kde.OAmigo"; path: "/OAmigo"; iface: "org.kde.OAmigo"
        function dbusStateChanged() { bridge.refresh(); }
    }
    Component.onCompleted: refresh()
}

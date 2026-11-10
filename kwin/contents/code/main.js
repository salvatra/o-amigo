"use strict";
// Event-driven: no cursor polling and no reservation of the other screen edges.
const service = "org.kde.OAmigo";
const path = "/OAmigo";
const iface = "org.kde.OAmigo";
let previous = null;
let popup = null;
let targetOutput = null;
let inside = false;
let hoverOutput = null;
let options = {hotspot_enabled: true, hotspot_width: 96};

function isAmigo(window) {
    return window && String(window.resourceClass).toLowerCase() === "org.kde.oamigo";
}
function isPopup(window) { return isAmigo(window) && String(window.caption) === "O Amigo"; }
function remember(window) {
    if (window && !isAmigo(window) && (window.normalWindow || window.dialog) && !window.skipSwitcher) previous = window;
}
function restore() {
    const active = workspace.activeWindow;
    if (active && !isPopup(active)) return;
    if (previous && workspace.stackingOrder.includes(previous) &&
        (previous.onAllDesktops || previous.desktops.includes(workspace.currentDesktop))) {
        previous.minimized = false; workspace.activeWindow = previous;
    }
}
function focus() {
    if (!popup || !workspace.stackingOrder.includes(popup)) return;
    popup.onAllDesktops = true; popup.skipTaskbar = true; popup.skipPager = true;
    popup.skipSwitcher = true; popup.keepAbove = true; popup.minimized = false;
    const output = workspace.screens.includes(targetOutput) ? targetOutput : workspace.activeScreen;
    const area = workspace.clientArea(KWin.PlacementArea, output, workspace.currentDesktop);
    const rect = popup.frameGeometry;
    rect.x = Math.round(area.x + (area.width - rect.width) / 2); rect.y = area.y + 4;
    popup.frameGeometry = rect;
    workspace.activeWindow = popup;
}
function attach(window) {
    if (!isPopup(window)) return;
    popup = window; focus();
}
function reload() {
    callDBus(service,path,iface,"IntegrationSettings",value => {
        try { options = JSON.parse(value); } catch (_) { return; }
        pointerChanged();
    });
}
function pointerChanged() {
    const point = workspace.cursorPos;
    const output = workspace.screens.find(screen => {
        const g = screen.geometry;
        const center = g.x + g.width / 2;
        return point.y >= g.y && point.y < g.y + 1 &&
            point.x >= center - options.hotspot_width / 2 && point.x < center + options.hotspot_width / 2;
    });
    const nowInside = !!output && !!options.hotspot_enabled;
    if (nowInside === inside && (!nowInside || output === hoverOutput)) return;
    if (inside && nowInside) callDBus(service,path,iface,"HotspotLeave");
    inside = nowInside;
    hoverOutput = output || null;
    if (inside) {
        remember(workspace.activeWindow); targetOutput = output;
        const area = workspace.clientArea(KWin.PlacementArea,output,workspace.currentDesktop);
        callDBus(service,path,iface,"HotspotEnter",Math.round(area.x),Math.round(area.y),Math.round(area.width),Math.round(area.height));
    } else callDBus(service,path,iface,"HotspotLeave");
}
workspace.windowActivated.connect(remember);
workspace.windowAdded.connect(attach);
workspace.windowRemoved.connect(window => {
    if (window === previous) previous = null;
    if (window === popup) { popup = null; restore(); }
});
workspace.cursorPosChanged.connect(pointerChanged);
remember(workspace.activeWindow);
for (const window of workspace.stackingOrder) attach(window);
registerShortcut("O Amigo Toggle","O Amigo: abrir / esconder","F12",() => {
    remember(workspace.activeWindow); targetOutput = workspace.activeScreen;
    const area = workspace.clientArea(KWin.PlacementArea,targetOutput,workspace.currentDesktop);
    callDBus(service,path,iface,"ToggleAt",Math.round(area.x),Math.round(area.y),Math.round(area.width),Math.round(area.height),visible => { if (visible) focus(); else restore(); });
});
registerShortcut("O Amigo Focus","O Amigo: ativar popup (interno)","",focus);
registerShortcut("O Amigo Restore Focus","O Amigo: restaurar foco (interno)","",restore);
registerShortcut("O Amigo Reload","O Amigo: atualizar integração (interno)","",reload);
reload();

from pathlib import Path
import unittest
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtQml import QJSEngine

APP=QCoreApplication.instance() or QCoreApplication([])

class HotspotTests(unittest.TestCase):
    def setUp(self):
        self.engine=QJSEngine()
        self.engine.evaluate('''var calls=[]; var shortcuts={};
        function signal(){return {connect:function(f){this.callback=f;}};}
        var workspace={cursorPos:{x:0,y:100},screens:[{geometry:{x:0,y:0,width:1440,height:900}},{geometry:{x:-1920,y:0,width:1920,height:1080}}],
          currentDesktop:{},stackingOrder:[],activeWindow:null,windowActivated:signal(),windowAdded:signal(),windowRemoved:signal(),cursorPosChanged:signal(),
          clientArea:function(kind,screen,desktop){var g=screen.geometry;return {x:g.x,y:g.y+30,width:g.width,height:g.height-30};}};
        var KWin={PlacementArea:0};
        function registerShortcut(name,label,key,callback){shortcuts[name]=callback;}
        function callDBus(service,path,iface,method){calls.push({method:method,args:Array.prototype.slice.call(arguments,4)});}
        function move(x,y){workspace.cursorPos={x:x,y:y};workspace.cursorPosChanged.callback();}
        ''')
        result=self.engine.evaluate((Path(__file__).resolve().parents[1]/'kwin/contents/code/main.js').read_text())
        self.assertFalse(result.isError(),result.toString());self.engine.evaluate('calls=[];')
    def methods(self):return self.engine.evaluate('calls.map(c=>c.method)').toVariant()
    def test_exact_96_pixel_zone_only_transitions(self):
        self.engine.evaluate('move(671,0);');self.assertEqual(self.methods(),[])
        self.engine.evaluate('move(672,0);move(720,0);move(767,0);');self.assertEqual(self.methods(),['HotspotEnter'])
        self.engine.evaluate('move(768,0);');self.assertEqual(self.methods(),['HotspotEnter','HotspotLeave'])
    def test_other_edges_unchanged_and_multiple_monitors(self):
        self.engine.evaluate('move(0,899);move(1439,899);move(1439,0);move(720,2);');self.assertEqual(self.methods(),[])
        self.engine.evaluate('move(-960,0);');self.assertEqual(self.methods(),['HotspotEnter'])
        self.assertEqual(self.engine.evaluate('calls[0].args').toVariant(),[-1920,30,1920,1050])
        self.engine.evaluate('move(720,0);');self.assertEqual(self.methods(),['HotspotEnter','HotspotLeave','HotspotEnter'])

if __name__=='__main__':unittest.main()

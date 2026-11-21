import json, os, sys, threading, time, tempfile, urllib.request, configparser
os.environ["QT_QPA_PLATFORM"]="offscreen"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mobase
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

class Mod:
    def __init__(s,name,path,sep=False): s.n=name; s.p=path; s.sep=sep
    def name(s): return s.n
    def isSeparator(s): return s.sep
    def isOverwrite(s): return False
    def isBackup(s): return False
    def isForeign(s): return False
    def absolutePath(s): return s.p
    def version(s): return mobase.VersionInfo("1.0")
    def nexusId(s): return 42
    def url(s): return ""
    def categories(s): return ["Fixes"]
    def installationFile(s): return "x.7z"
    def comments(s): return ""
    def notes(s): return ""

class ModList:
    def __init__(s, root):
        s.order=["Extenders_separator","SKSE","Address Library","Fixes_separator","SSE Engine Fixes","Unused"]
        s.active={"SKSE","Address Library","SSE Engine Fixes"}
        s.mods={}
        for n in s.order:
            p=os.path.join(root,n); os.makedirs(p,exist_ok=True)
            if n=="SSE Engine Fixes": open(os.path.join(p,"EngineFixes.esp"),"w").close()
            if n in ("SKSE","SSE Engine Fixes"): open(os.path.join(p,"engine.ini"),"w").close()
            if n=="SKSE": open(os.path.join(p,"skse64_loader.exe"),"w").close()
            if n=="SSE Engine Fixes":
                open(os.path.join(p,"old.esp.mohidden"),"w").close()
                os.makedirs(os.path.join(p,"Textures.mohidden","sub"),exist_ok=True)
                open(os.path.join(p,"Textures.mohidden","sub","a.dds"),"w").close()
            s.mods[n]=Mod(n,p,n.endswith("_separator"))
    def allMods(s): return list(s.order)
    def allModsByProfilePriority(s, profile=None): return list(s.order)
    def getMod(s,n): return s.mods.get(n)
    def priority(s,n): return s.order.index(n)
    def state(s,n): return mobase.ModState.EXISTS | (mobase.ModState.ACTIVE if n in s.active else 0)
    def setActive(s,names,a):
        for n in names: (s.active.add if a else s.active.discard)(n)
        return len(names)
    def setPriority(s,n,p):
        s.order.remove(n); s.order.insert(p,n); return True
    def renameMod(s,mod,new):
        old=mod.name(); i=s.order.index(old); newp=os.path.join(os.path.dirname(mod.absolutePath()),new)
        os.rename(mod.absolutePath(),newp); m=Mod(new,newp,new.endswith("_separator"))
        s.order[i]=new; del s.mods[old]; s.mods[new]=m
        if old in s.active: s.active.discard(old); s.active.add(new)
        return m

class PluginList:
    def __init__(s): s.order=["Skyrim.esm","Update.esm","EngineFixes.esp"]; s.st={p:mobase.PluginState.ACTIVE for p in s.order}; s.light=set(); s.mast={}
    def pluginNames(s): return list(s.order)
    def priority(s,n): return s.order.index(n)
    def loadOrder(s,n): return s.order.index(n) if s.st[n]==mobase.PluginState.ACTIVE else -1
    def state(s,n): return s.st[n]
    def setState(s,n,v): s.st[n]=v
    def setPriority(s,n,p): s.order.remove(n); s.order.insert(p,n); return True
    def isMasterFlagged(s,n): return n.endswith(".esm")
    def hasMasterExtension(s,n): return n.endswith(".esm")
    def isLightFlagged(s,n): return n in s.light
    def masters(s,n): return s.mast.get(n, [])
    def hasLightExtension(s,n): return False
    def isMediumFlagged(s,n): return False
    def hasNoRecords(s,n): return False
    def origin(s,n): return "data" if n.endswith(".esm") else "SSE Engine Fixes"

class Game:
    def gameName(s): return "Skyrim Special Edition"
    def gameVersion(s): return "1.6.1170"
    def __init__(s, root="/tmp"): s.root = root
    def gameDirectory(s):
        from PyQt6.QtCore import QDir; return QDir("/game")
    def dataDirectory(s):
        from PyQt6.QtCore import QDir; return QDir(os.path.join(s.root, "gamedata"))
    def documentsDirectory(s):
        from PyQt6.QtCore import QDir; return QDir(os.path.join(s.root, "docs"))

class Profile:
    def localSavesEnabled(s): return True
    def localSettingsEnabled(s): return True

class Org:
    def __init__(s, root):
        s.root=root; s.ml=ModList(os.path.join(root,"mods")); s.pl=PluginList(); s.refreshed=0; s.started=[]
        os.makedirs(os.path.join(root,"overwrite"),exist_ok=True)
        os.makedirs(os.path.join(root,"logs"),exist_ok=True)
        with open(os.path.join(root,"logs","mo_interface.log"),"w") as f:
            f.write("\n".join(f"[I] line {i}" for i in range(10))+"\n[W] plugin warning here\n")
        s.pending=[]; s.on_refresh=[]
        s.profile_name="Step"; s.manage_opened=False; s.plugin_files={}
        for prof in ("Step","Mod Dev"): os.makedirs(os.path.join(root,"profiles",prof),exist_ok=True); s.dm=DownloadManager(root)
        with open(os.path.join(root,"ModOrganizer.ini"),"w") as f:
            f.write("[customExecutables]\nsize=2\n1\\title=SSEEdit\n1\\binary=H:/Tools/SSEEdit/SSEEdit.exe\n1\\arguments=\n1\\workingDirectory=\n2\\title=LOOT\n2\\binary=H:/Tools/LOOT/LOOT.exe\n2\\arguments=\n2\\workingDirectory=\n")
    def modList(s): return s.ml
    def pluginList(s): return s.pl
    def managedGame(s): return Game(s.root)
    def profile(s): return Profile()
    def appVersion(s): return mobase.VersionInfo("2.5.2")
    def basePath(s): return s.root
    def modsPath(s): return os.path.join(s.root,"mods")
    def downloadsPath(s): return os.path.join(s.root,"downloads")
    def overwritePath(s): return os.path.join(s.root,"overwrite")
    def profileName(s): return s.profile_name
    def profilePath(s): return os.path.join(s.root,"profiles",s.profile_name)
    def pluginSetting(s,p,k): return {"port": 52599, "extra_instructions": "Follow the Step guide."}[k]
    def onUserInterfaceInitialized(s,cb): return True
    def getFileOrigins(s,p):
        return [n for n in reversed(s.ml.order) if n in s.ml.active and os.path.exists(os.path.join(s.ml.mods[n].absolutePath(),p))]
    def resolvePath(s,p): return s.plugin_files.get(p, "/x/"+p)
    def refresh(s,save=True):
        s.refreshed+=1
        for n in s.pending:
            p=os.path.join(s.modsPath(),n); s.ml.order.append(n); s.ml.mods[n]=Mod(n,p,n.endswith("_separator"))
        s.pending=[]
        cbs, s.on_refresh = s.on_refresh, []
        for cb in cbs: cb()
    def onNextRefresh(s,cb,immediate=True): s.on_refresh.append(cb); return True
    def createMod(s,name):
        p=os.path.join(s.modsPath(),str(name)); os.makedirs(p); s.pending.append(str(name)); return Mod(str(name),p,str(name).endswith("_separator"))
    def startApplication(s,exe,args=[],cwd=""): s.started.append(exe); return 1234
    def installMod(s,path,name=""): return None
    def downloadManager(s): return s.dm

class DownloadManager:
    """Fake: file 1 lands after a moment (with MO2's .meta), file 3 never finishes.
    Like the real MO2, the returned id says nothing about which file in the folder it is."""
    def __init__(s, root): s.root=root; s.started=[]
    def startDownloadNexusFile(s,mod_id,file_id):
        s.started.append((mod_id,file_id))
        folder=os.path.join(s.root,"downloads")
        def land():
            name=f"Mod {mod_id}-{file_id}.7z"
            open(os.path.join(folder,name),"w").close()
            with open(os.path.join(folder,name+".meta"),"w") as f: f.write(f"[General]\nmodID={mod_id}\nfileID={file_id}\n")
        if file_id==1: QTimer.singleShot(300, land)
        return 481

class FakeBackend:
    def __init__(s): s.alive=True
    def pid_from_handle(s,h): return 999
    def open(s,pid): return 7
    def exit_code(s,h): return None if s.alive else 0
    def close(s,h): pass

app = QApplication([])
tmp = tempfile.mkdtemp()
from mo2_mcp import plugin as P
P.CONNECTION_FILE = P.Path(tmp)/"connection.json"; P.TOOLS_CACHE=P.Path(tmp)/"tools.json"
from mo2_mcp.procs import RunTracker
plug = P.McpPlugin()
backend = FakeBackend(); plug._runs = RunTracker(backend)
org = Org(tmp)
assert plug.init(org)
# A stand-in for MO2's main window: its profile box behaves like MO2's on_profileBox_currentIndexChanged.
from PyQt6.QtWidgets import QMainWindow, QComboBox
win = QMainWindow(); box = QComboBox(win); box.setObjectName("profileBox")
box.addItems(["<Manage...>", "Mod Dev", "Step"]); box.setCurrentText("Step")
def on_profile(index):
    if index == 0: org.manage_opened = True
    else: org.profile_name = box.itemText(index); org.refresh()
box.currentIndexChanged.connect(on_profile)
# ...and its notifications button, which opens a modal ProblemsDialog like MO2's on_actionNotifications_triggered.
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QDialog, QTreeWidget, QTreeWidgetItem, QPushButton
from PyQt6.QtCore import Qt
notif = QAction(win); notif.setObjectName("actionNotifications"); notif.setEnabled(False)
problems_seen = {"opened": 0, "left_open": False}
def open_problems():
    problems_seen["opened"] += 1
    dlg = QDialog(win); dlg.setObjectName("ProblemsDialog")
    tree = QTreeWidget(dlg); tree.setObjectName("problemsWidget"); tree.setColumnCount(2)
    a = QTreeWidgetItem(); a.setText(0, "Files in Overwrite"); a.setData(0, Qt.ItemDataRole.UserRole, "There are <b>3</b> files in Overwrite.")
    a.setText(1, "No guided fix"); tree.addTopLevelItem(a)
    b = QTreeWidgetItem(); b.setText(0, "Missing master"); b.setData(0, Qt.ItemDataRole.UserRole, "X.esp needs Y.esm")
    tree.addTopLevelItem(b); tree.setItemWidget(b, 1, QPushButton("Fix"))
    dlg.exec()
    problems_seen["left_open"] = dlg.isVisible()
notif.triggered.connect(open_problems)
plug._confirm_install = lambda a,n: False  # simulate "No" in the dialog
# rebuild server so the patched confirm is used
plug.stop(); plug.start()
conn = json.loads(P.CONNECTION_FILE.read_text())
results = {}; failures=[]

def rpc(method, params=None, id_=1, token=None, host=None):
    body = {"jsonrpc":"2.0","method":method}
    if id_ is not None: body["id"]=id_
    if params is not None: body["params"]=params
    req = urllib.request.Request(f"http://127.0.0.1:{conn['port']}/mcp", data=json.dumps(body).encode(), method="POST",
        headers={"X-MO2-Token": token or conn["token"], "Content-Type":"application/json", **({"Host":host} if host else {})})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw=r.read(); return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e: return e.code, None

def call(name, args=None):
    st, r = rpc("tools/call", {"name":name,"arguments":args or {}})
    assert st==200, st
    return r["result"]["isError"], r["result"]["content"][0]["text"]

def check(label, cond):
    print(("PASS " if cond else "FAIL ")+label); 
    if not cond: failures.append(label)

def client():
    try:
        st,r = rpc("initialize", {"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"1"}})
        check("initialize", st==200 and r["result"]["protocolVersion"]=="2025-06-18")
        check("extra instructions appended", r["result"]["instructions"].endswith("Follow the Step guide."))
        check("notification -> 202", rpc("notifications/initialized", id_=None)[0]==202)
        check("bad token -> 401", rpc("ping", token="x"*40)[0]==401)
        check("bad host -> 404", rpc("ping", host="evil.com")[0]==404)
        req = urllib.request.Request(f"http://127.0.0.1:{conn['port']}/mcp", data=b'{"jsonrpc":"2.0","id":9,"method":"ping"}', method="POST",
            headers={"X-MO2-Token": conn["token"], "Origin": "https://evil.example"})
        try: urllib.request.urlopen(req, timeout=5); code = 200
        except urllib.error.HTTPError as e: code = e.code
        check("browser Origin -> 403", code==403)
        st,r = rpc("tools/list"); names=[t["name"] for t in r["result"]["tools"]]
        check("tools/list has 30 tools", len(names)==30)
        e,t = call("get_status"); s=json.loads(t)
        check("get_status counts", not e and s["mods"]=={"total":4,"enabled":3,"separators":2} and s["plugins"]["enabled"]==3)
        e,t = call("list_mods", {"separator":"Fixes"}); print(t)
        check("list_mods separator filter", "SSE Engine Fixes" in t and "SKSE" not in t and "- Unused" in t)
        e,t = call("list_plugins"); print(t)
        check("list_plugins", "[M]" in t and "EngineFixes.esp <- SSE Engine Fixes" in t)
        e,t = call("get_mod", {"name":"sse engine fixes","list_files":True})
        m = json.loads(t)
        check("get_mod case-insensitive + plugins", not e and m["plugins"]==["EngineFixes.esp"])
        check("get_mod leaves out files MO2 hides", m["file_count"]==2 and m["hidden_by_mo2"]==2
              and m["hidden_files"]==["Textures.mohidden/", "old.esp.mohidden"] and not any("mohidden" in f for f in m["files"]))
        e,t = call("get_mod", {"name":"nope"}); check("get_mod unknown -> isError", e)
        e,t = call("get_mod_conflicts", {"name":"SSE Engine Fixes"}); c=json.loads(t)
        check("conflicts: Engine Fixes overrides SKSE", not e and c["overrides"][0]["mod"]=="SKSE" and c["overrides"][0]["examples"]==["engine.ini"])
        e,t = call("get_mod_conflicts", {"name":"SKSE"}); c=json.loads(t)
        check("conflicts: SKSE overridden by Engine Fixes, 1 unique file", c["overridden_by"][0]["mod"]=="SSE Engine Fixes" and c["files_without_conflict"]==1)
        e,t = call("get_mod_conflicts", {"name":"Unused"}); check("conflicts of disabled mod refused", e and "disabled" in t)
        e,t = call("read_log", {"lines":3}); check("read_log tail", not e and t.splitlines()[-1]=="[W] plugin warning here" and "last 3 of 11" in t)
        e,t = call("read_log", {"contains":"warning"}); check("read_log filter", "last 1 of 1" in t)
        e,t = call("read_log", {"log":"usvfs"}); check("read_log no usvfs -> isError", e)
        before=org.refreshed
        e,t = call("refresh"); check("refresh waits for completion", not e and t=="MO2 refreshed." and org.refreshed==before+1)
        e,t = call("create_separator", {"name":"Testing Area","after":"Address Library"}); r=json.loads(t)
        check("create separator placed after mod", not e and org.ml.order[3]=="Testing Area_separator" and org.ml.mods["Testing Area_separator"].isSeparator())
        e,t = call("create_separator", {"name":"Testing Area"}); check("duplicate separator refused", e and "already exists" in t)
        e,t = call("create_separator", {"name":"bad/name"}); check("bad separator name refused", e and "Invalid name" in t)
        e,t = call("rename_mod", {"name":"Testing Area","new_name":"Test Zone"}); r=json.loads(t)
        check("rename separator keeps suffix", not e and r["new"]=="Test Zone_separator" and org.ml.order[3]=="Test Zone_separator")
        e,t = call("rename_mod", {"name":"Unused","new_name":"SKSE"}); check("rename onto existing name refused", e and "already exists" in t)
        e,t = call("set_mod_priority", {"name":"Test Zone","priority":6}); check("move separator to end", org.ml.order[-1]=="Test Zone_separator")
        # -- profiles --
        e,t = call("list_profiles"); r=json.loads(t)
        check("list_profiles", not e and r["active"]=="Step" and [x["name"] for x in r["profiles"]]==["Mod Dev","Step"])
        e,t = call("switch_profile", {"name":"Mod Dev"}); check("switch before MO2's window is up refused", e and "not ready" in t)
        plug._on_ui(win)
        e,t = call("switch_profile", {"name":"Nope"}); check("unknown profile refused", e and "Profiles: Mod Dev, Step" in t)
        e,t = call("switch_profile", {"name":"<Manage...>"}); check("<Manage...> is never picked", e and not org.manage_opened)
        e,t = call("switch_profile", {"name":"step"}); check("already active profile is a no-op", not e and "already active" in t)
        box.setEnabled(False)
        e,t = call("switch_profile", {"name":"Mod Dev"}); check("locked profile box refused", e and "locked" in t and org.profile_name=="Step")
        box.setEnabled(True)
        before=org.refreshed
        e,t = call("switch_profile", {"name":"mod dev"}); r=json.loads(t)
        check("switch profile (case-insensitive) and wait for refresh",
              not e and r=={"previous":"Step","profile":"Mod Dev","refreshed":True} and org.refreshed>=before+2 and not org.manage_opened)
        e,t = call("switch_profile", {"name":"Step"}); check("switch back", not e and org.profile_name=="Step")
        # -- notifications --
        e,t = call("list_notifications"); check("no notifications when MO2's button is off", not e and json.loads(t)=={"count":0,"notifications":[]} and problems_seen["opened"]==0)
        notif.setEnabled(True)
        e,t = call("list_notifications"); r=json.loads(t)
        check("notifications read from MO2's window, which is closed again",
              not e and r["count"]==2 and r["notifications"][0]=={"problem":"Files in Overwrite","details":"There are 3 files in Overwrite.","guided_fix_in_mo2":False}
              and r["notifications"][1]["guided_fix_in_mo2"] and problems_seen["opened"]==1 and not problems_seen["left_open"])
        # -- create_mod_from_overwrite --
        ow = org.overwritePath()
        e,t = call("create_mod_from_overwrite", {"name":"LOD Output"}); check("empty Overwrite refused", e and "empty" in t)
        def put(rel, text="x"):
            path = os.path.join(ow, *rel.split("/")); os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f: f.write(text)
        for rel in ("meshes/lod/a.nif", "textures/lod/b.dds", "DynDOLOD.esp", "SKSE/Plugins/x.ini"): put(rel)
        e,t = call("create_mod_from_overwrite", {"name":"LOD Output","dry_run":True}); r=json.loads(t)
        check("dry run lists 4 files and moves nothing", not e and r["dry_run"] and r["file_count"]==4
              and os.path.exists(os.path.join(ow,"DynDOLOD.esp")) and "LOD Output" not in org.ml.order)
        e,t = call("create_mod_from_overwrite", {"name":"TexGen Output","only":["Textures"],"after":"Address Library"}); r=json.loads(t)
        tex = os.path.join(org.modsPath(),"TexGen Output","textures","lod","b.dds")
        check("only= moves one folder into a new, enabled, placed mod",
              not e and r["moved"]==1 and os.path.isfile(tex) and not os.path.exists(os.path.join(ow,"textures"))
              and r["enabled"] and org.ml.order.index("TexGen Output")==org.ml.order.index("Address Library")+1)
        e,t = call("create_mod_from_overwrite", {"name":"X","only":["nope"]}); check("unknown only= entry refused", e and "Not in Overwrite" in t and "meshes" in t)
        e,t = call("create_mod_from_overwrite", {"name":"SKSE"}); check("new mod over existing name refused", e and "already exists" in t)
        e,t = call("create_mod_from_overwrite", {"name":"Extenders","into_existing":True}); check("moving into a separator refused", e and "cannot receive" in t)
        put("engine.ini", "new")
        e,t = call("create_mod_from_overwrite", {"name":"SKSE","into_existing":True,"only":["engine.ini"]})
        check("clash in existing mod refused, file kept", e and "already exist" in t and os.path.exists(os.path.join(ow,"engine.ini")))
        was_active = "SKSE" in org.ml.active
        e,t = call("create_mod_from_overwrite", {"name":"SKSE","into_existing":True,"replace_files":True}); r=json.loads(t)
        with open(os.path.join(org.modsPath(),"SKSE","engine.ini")) as f: replaced_text = f.read()
        check("into_existing moves the rest and replaces with replace_files",
              not e and r["moved"]==4 and r["replaced"]==1 and replaced_text=="new" and os.listdir(ow)==[]
              and os.path.isfile(os.path.join(org.modsPath(),"SKSE","meshes","lod","a.nif"))
              and ("SKSE" in org.ml.active)==was_active and "enabled" not in r)
        e,t = call("file_origins", {"path":"Data/engine.ini"}); check("file_origins", json.loads(t)["winner"]=="SSE Engine Fixes")
        e,t = call("list_executables"); check("list_executables", [x["title"] for x in json.loads(t)]==["SSEEdit","LOOT"])
        e,t = call("set_mods_enabled", {"names":["Unused"],"enabled":True}); check("enable mod", json.loads(t)=={"Unused":True})
        e,t = call("set_mod_priority", {"name":"Unused","after":"Extenders"}); check("move after separator", org.ml.order[1]=="Unused")
        e,t = call("set_mod_priority", {"name":"Unused","after":"SSE Engine Fixes"}); check("move after mod (downwards)", org.ml.order.index("Unused")==org.ml.order.index("SSE Engine Fixes")+1)
        e,t = call("set_plugins_enabled", {"names":["enginefixes.esp"],"enabled":False}); check("disable plugin", json.loads(t)=={"EngineFixes.esp":False})
        st,r = rpc("tools/call", {"name":"set_mods_enabled","arguments":{"names":"x","enabled":True}})
        check("bad argument type -> isError tool result", r["result"]["isError"] and "must be array" in r["result"]["content"][0]["text"])
        st,r = rpc("tools/call", {"name":"get_mod","arguments":{}})
        check("missing argument -> isError tool result", r["result"]["isError"] and "missing required argument 'name'" in r["result"]["content"][0]["text"])
        st,r = rpc("tools/call", {"name":"get_mod","arguments":{"name":"SKSE","bogus":1}})
        check("unknown argument -> isError tool result", r["result"]["isError"] and "unknown argument 'bogus'" in r["result"]["content"][0]["text"])
        st,r = rpc("tools/call", {"name":"no_such_tool","arguments":{}})
        check("unknown tool stays a protocol error", r.get("error",{}).get("code")==-32602)
        e,t = call("run_executable", {"executable":"notepad"}); check("unknown exe refused", e)
        e,t = call("run_executable", {"executable":"sseedit","args":["-qac"]}); run=json.loads(t)
        check("run SSEEdit by title", not e and org.started==["SSEEdit"] and run["status"]=="running")
        e,t = call("set_mods_enabled", {"names":["Unused"],"enabled":False}); check("writes blocked while running", e and "still running" in t)
        e,t = call("get_status"); check("reads allowed while running", not e)
        e,t = call("wait_for_run", {"run_id":run["run_id"],"timeout_seconds":1}); check("wait timeout keeps running", json.loads(t)["status"]=="running")
        backend.alive=False
        before=org.refreshed
        e,t = call("wait_for_run", {"run_id":run["run_id"],"timeout_seconds":5}); r2=json.loads(t)
        check("wait finished + refresh", r2["status"]=="finished" and r2["exit_code"]==0 and org.refreshed==before+1)
        e,t = call("run_executable", {"executable":"LOOT"})
        check("run by exact-case title", not e and org.started==["SSEEdit","LOOT"])
        os.makedirs(org.downloadsPath(),exist_ok=True); open(os.path.join(org.downloadsPath(),"a.7z"),"w").close()
        e,t = call("install_mod", {"archive":"a.7z"}); check("install declined in dialog -> isError", e and "declined" in t)
        e,t = call("install_mod", {"archive":"missing.7z"}); check("install missing archive", e and "not found" in t)
        dl=org.downloadsPath()
        old=os.path.join(dl,"Old copy.7z"); open(old,"w").close()  # an earlier download of the same file
        with open(old+".meta","w") as f: f.write("[General]\nmodID=199063\nfileID=1\n")
        os.utime(old,(1,1))
        e,t = call("download_mod", {"mod_id":199063,"file_id":1,"wait_seconds":10}); d=json.loads(t)
        check("download found by .meta, not by MO2's id", not e and d["status"]=="complete" and d["archive"]=="Mod 199063-1.7z"
              and org.dm.started==[(199063,1)])
        e,t = call("download_mod", {"mod_id":196070,"file_id":3,"wait_seconds":1}); d=json.loads(t)
        check("slow download keeps going", not e and d["status"]=="not finished" and "wait_for_download" in d["note"])
        e,t = call("wait_for_download", {"download_id":d["download_id"],"timeout_seconds":1})
        check("wait_for_download still not finished", not e and json.loads(t)["status"]=="not finished")
        e,t = call("wait_for_download", {"download_id":99}); check("wait for unknown download refused", e and "Unknown" in t)
        e,t = call("download_mod", {"mod_id":0,"file_id":5}); check("bad mod id refused", e and "positive" in t)
        # -- SKSE plugins --
        from mo2_mcp.skse import parse_skse_log
        sample = parse_skse_log("SKSE64 runtime: initialize (version = 2.3.1 01070680 01DD, os = 6.2 (9200))\n"
            "plugin DP_Extender.dll (00000001 DP_Extender - Dynamic Potions Extender (by egocarib) 00000002) loaded correctly (handle 10)\n"
            "plugin msdia140.dll (00000000  00000000) no version data 0 (handle 0)\n"
            "couldn't load plugin Bad.dll (Error 126)")
        dp, ms, bad = sample.entries["dp_extender.dll"], sample.entries["msdia140.dll"], sample.entries["bad.dll"]
        check("SKSE log parser: names with brackets, failures, version",
              sample.skse_version=="2.3.1" and dp.loaded and dp.name=="DP_Extender - Dynamic Potions Extender (by egocarib)" and dp.version=="2 (0x00000002)"
              and not ms.loaded and ms.result=="no version data 0" and ms.helper and not dp.helper and not bad.loaded and "Error 126" in bad.result)
        def dll(folder, *rel):
            path = os.path.join(folder, *rel); os.makedirs(os.path.dirname(path), exist_ok=True); open(path, "w").close()
        mods = org.modsPath()
        dll(mods, "SSE Engine Fixes", "SKSE", "Plugins", "EngineFixes.dll")
        dll(mods, "SSE Engine Fixes", "SKSE", "Plugins", "New.dll")
        dll(mods, "SKSE", "SKSE", "Plugins", "EngineFixes.dll")
        dll(mods, "Address Library", "SKSE", "Plugins", "Broken.dll")
        dll(mods, "Unused", "skse", "plugins", "Old.dll")
        org.ml.active.discard("Unused")
        dll(os.path.join(tmp, "gamedata"), "SKSE", "Plugins", "Base.dll")
        os.makedirs(os.path.join(tmp, "docs", "SKSE"), exist_ok=True)
        e,t = call("list_skse_plugins"); check("no SKSE log yet is reported", not e and json.loads(t)["skse_log"].startswith("not found"))
        with open(os.path.join(tmp, "docs", "SKSE", "skse64.log"), "w") as f:
            f.write("SKSE64 runtime: initialize (version = 2.3.1 01070680 01DD79A2B00F2F7D, os = 6.2 (9200))\n"
                    "checking plugin Base.dll\nchecking plugin Broken.dll\nchecking plugin EngineFixes.dll\nchecking plugin Gone.dll\n"
                    "plugin Base.dll (00000001 Base 01000000) loaded correctly (handle 1)\n"
                    "plugin Broken.dll (00000001 Broken Thing 01000000) reported as incompatible during query (handle 2)\n"
                    "plugin EngineFixes.dll (00000001 EngineFixes 07000000) loaded correctly (handle 3)\n")
        e,t = call("list_skse_plugins"); r=json.loads(t)
        by = {(x["dll"], x["mod"]): x for x in r["plugins"]}
        check("SKSE overview: loaded, overridden, failed, missing from log, disabled, game folder",
              not e and r["skse_version"]=="2.3.1" and r["summary"]=={"dlls":6,"in_enabled_mods":4,"loaded":2,"problems":2,"in_disabled_mods":1}
              and by[("EngineFixes.dll","SSE Engine Fixes")]["status"]=="loaded" and by[("EngineFixes.dll","SSE Engine Fixes")]["version"]=="7.0.0 (0x07000000)"
              and by[("EngineFixes.dll","SKSE")]["status"]=="overridden by SSE Engine Fixes"
              and by[("Broken.dll","Address Library")]["status"]=="not loaded: reported as incompatible during query"
              and by[("New.dll","SSE Engine Fixes")]["status"].startswith("not in the SKSE log")
              and by[("Old.dll","Unused")]["status"]=="mod disabled"
              and by[("Base.dll","(game Data folder)")]["status"]=="loaded"
              and r["in_log_but_not_found"]==["Gone.dll"])
        e,t = call("list_skse_plugins", {"problems_only":True}); check("SKSE problems_only", sorted(x["dll"] for x in json.loads(t)["plugins"])==["Broken.dll","New.dll"])
        e,t = call("list_skse_plugins", {"enabled_only":True,"filter":"engine"}); check("SKSE filters (text matches DLL or mod name)", len(json.loads(t)["plugins"])==3)
        # -- plugin headers / light candidates --
        import struct
        def plugin_bytes(masters, records, flags=0, version=1.71):
            subs = b"HEDR" + struct.pack("<HfII", 12, version, len(records), 0x800)
            for m in masters:
                z = m.encode() + b"\0"
                subs += b"MAST" + struct.pack("<H", len(z)) + z + b"DATA" + struct.pack("<H", 8) + b"\0" * 8
            data = b"TES4" + struct.pack("<IIIIHH", len(subs), flags, 0, 0, 44, 0) + subs
            groups = {}
            for kind, fid in records: groups.setdefault(kind, []).append(fid)
            for kind, fids in groups.items():
                body = b"".join(kind + struct.pack("<IIIIHH", 4, 0, fid, 0, 44, 0) + b"\0" * 4 for fid in fids)
                data += b"GRUP" + struct.pack("<I4sIHHHH", 24 + len(body), kind, 0, 0, 0, 0, 0) + body
            return data
        pdir = os.path.join(tmp, "plugin_files"); os.makedirs(pdir, exist_ok=True)
        def add_plugin(name, content, masters=(), light=False):
            path = os.path.join(pdir, name)
            with open(path, "wb") as f: f.write(content)
            org.pl.order.append(name); org.pl.st[name] = mobase.PluginState.ACTIVE; org.pl.mast[name] = list(masters)
            org.plugin_files[name] = path
            if light: org.pl.light.add(name)
        sky = ["Skyrim.esm"]
        add_plugin("AsIs.esp", plugin_bytes(sky, [(b"WEAP", 0x01000800), (b"WEAP", 0x01000801), (b"NPC_", 0x00012345)]), sky)
        add_plugin("Overrides.esp", plugin_bytes(sky + ["Update.esm"], [(b"NPC_", 0x00012345), (b"NPC_", 0x01000F00)]), sky + ["Update.esm"])
        add_plugin("Old170.esp", plugin_bytes(sky, [(b"MISC", 0x01000010), (b"MISC", 0x01000020)], version=1.70), sky)
        add_plugin("Big.esp", plugin_bytes(sky, [(b"MISC", 0x01000900), (b"MISC", 0x01001234)]), sky)
        add_plugin("Dependent.esp", plugin_bytes(sky + ["Big.esp"], [(b"MISC", 0x01001234)]), sky + ["Big.esp"])
        add_plugin("Cells.esp", plugin_bytes(sky, [(b"CELL", 0x01000900)]), sky)
        add_plugin("TooMany.esp", plugin_bytes(sky, [(b"MISC", 0x01000000 + i) for i in range(0x800, 0x800 + 4097)]), sky)
        add_plugin("Light.esp", plugin_bytes(sky, [(b"MISC", 0x01000800)], flags=0x200), sky, light=True)
        add_plugin("Broken.esp", b"not a plugin at all, just text", sky)
        e,t = call("plugin_header", {"names":["asis.esp","Light.esp","Broken.esp","Big.esp"]}); r=json.loads(t)
        by = {x["plugin"]: x for x in r["plugins"]}
        a = by["AsIs.esp"]
        check("plugin_header reads header, masters and counts",
              not e and a["header_version"]==1.71 and a["masters"]==["Skyrim.esm"] and a["records"]==3 and a["new_records"]==2
              and a["new_id_range"]=="0x000800-0x000801" and a["light"]=="flag_as_is" and a["flags"]=="")
        check("plugin_header: already light, broken file, compacting with dependents",
              by["Light.esp"]["light"]=="already_light" and "TES4" in by["Broken.esp"]["error"]
              and by["Big.esp"]["light"]=="needs_compacting" and by["Big.esp"]["used_as_master_by"]==["Dependent.esp"]
              and "summary" not in r)
        e,t = call("plugin_header"); r=json.loads(t)
        by = {x["plugin"]: x for x in r["plugins"]}
        check("plugin_header without names skips official, disabled and light plugins",
              not e and set(by)=={"AsIs.esp","Overrides.esp","Old170.esp","Big.esp","Dependent.esp","Cells.esp","TooMany.esp","Broken.esp"})
        check("light verdicts: overrides only, header 1.70, too many, new cells",
              by["Overrides.esp"]["light"]=="flag_as_is" and by["Overrides.esp"]["new_records"]==0
              and by["Old170.esp"]["light"]=="needs_header_171" and by["TooMany.esp"]["light"]=="too_many"
              and by["Cells.esp"]["light"]=="flag_as_is" and "1 new cell" in by["Cells.esp"]["why"]
              and by["Dependent.esp"]["light"]=="flag_as_is")
        check("light summary counts full plugin slots",
              r["summary"]=={"enabled_full_plugins":10,"enabled_light_plugins":1,"full_plugin_limit":254,
                             "could_be_flagged_light_as_is":4,"full_plugins_if_flagged":6})
        e,t = call("plugin_header", {"candidates_only":True})
        check("candidates_only", sorted(x["plugin"] for x in json.loads(t)["plugins"])==["AsIs.esp","Cells.esp","Dependent.esp","Old170.esp","Overrides.esp"])
        # -- generated output out of date? --
        T0 = time.time() + 100000  # in the future, so files from earlier tests are older
        def add_mod(name, files, active=True):
            root = os.path.join(org.modsPath(), name)
            for rel, (content, age) in files.items():
                path = os.path.join(root, *rel.split("/")); os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f: f.write(content if isinstance(content, bytes) else content.encode())
                os.utime(path, (T0 + age, T0 + age))
            org.ml.order.append(name); org.ml.mods[name] = Mod(name, root)
            if active: org.ml.active.add(name)
        add_mod("Pandora_Output", {"meshes/animationdatasinglefile.txt": ("x", 0), "Engine.log": ("ok", 1),
                                   "Pandora_Engine/ActiveMods.json": ('[{"code":"isffr","active":true,"priority":1},'
                                                                      '{"code":"oldp","active":true,"priority":2}]', 0)})
        add_mod("Ice Skating", {"Nemesis_Engine/mod/isffr/info.ini": ("name=Ice skating fixed\nauthor=x\n", -500)})
        add_mod("New Behavior", {"meshes/actors/character/behaviors/0_master.hkx": ("b", 1000),
                                 "Nemesis_Engine/mod/newp/info.ini": ("name=New Patch\n", 1000)})
        add_mod("OAR Anims", {"meshes/actors/character/animations/OpenAnimationReplacer/a/x.hkx": ("a", 1000)})
        add_mod("Step - TexGen_Output", {"textures/lod/rock.dds": ("t", 500)})
        add_mod("Step - DynDOLOD_Output", {"DynDOLOD.esp": (plugin_bytes(["Skyrim.esm", "Gone.esp"], []), 0),
                                           "meshes/lod/x.nif": ("m", 0)})
        add_mod("Tex Mod", {"textures/rocks/rock.dds": ("r", 1100), "textures/rocks/old.dds.mohidden": ("h", 9000),
                            "textures/effects/fx.dds": ("e", 1100)})
        add_mod("Late Plugin", {"Late.esp": (plugin_bytes(["Skyrim.esm"], [(b"WRLD", 0x01000800)]), 2000)})
        add_mod("Quest Plugin", {"Quest.esp": (plugin_bytes(["Skyrim.esm"], [(b"QUST", 0x01000800)]), 2000),
                                 "Occlusion.esp": (plugin_bytes(["Skyrim.esm"], [(b"WRLD", 0x01000801)]), 2000)})
        add_mod("Disabled Tex", {"textures/lod/z.dds": ("z", 3000)}, active=False)
        add_mod("xEdit_Output", {"SSEEdit Cache/x.refcache": ("c", 4000)})
        for pname in ("DynDOLOD.esp", "Late.esp"):
            org.pl.order.append(pname); org.pl.st[pname] = mobase.PluginState.ACTIVE
        with open(os.path.join(org.profilePath(), "modlist.txt"), "w") as f: f.write("+x\n")
        os.utime(os.path.join(org.profilePath(), "modlist.txt"), (T0 + 3000, T0 + 3000))
        e,t = call("check_outputs"); r=json.loads(t)
        by = {x["mod"]: x for x in r.get("outputs", [])}
        check("check_outputs finds and orders outputs, skips unknown ones",
              not e and [x["mod"] for x in r["outputs"] if x["mod"]!="TexGen Output"]==["Step - TexGen_Output","Step - DynDOLOD_Output","Pandora_Output"]
              and {"mod":"xEdit_Output","why":"not recognized as Pandora, PGPatcher, xLODGen, TexGen or DynDOLOD output"} in r["not_checked"])
        pa = by["Pandora_Output"]
        check("Pandora: behavior files and patches, not plain animations",
              pa["made_by"]=="Pandora" and pa["verdict"]=="out of date: rerun Pandora"
              and [c["mod"] for c in pa["changed_mods"]]==["New Behavior"] and pa["changed_mods"][0]["files"]==2
              and pa["patches_in_last_run"]==["Ice skating fixed","oldp"] and pa["patches_gone"]==["oldp"]
              and pa["patches_not_in_last_run"]==[{"patch":"New Patch","mod":"New Behavior"}]
              and pa["profile_saved_after"]==["modlist.txt"])
        dy = by["Step - DynDOLOD_Output"]
        check("DynDOLOD: newer TexGen output and plugin, missing master, plugins after it",
              dy["verdict"]=="out of date: rerun DynDOLOD"
              and sorted(c["mod"] for c in dy["changed_mods"])==["Late Plugin","Step - TexGen_Output"]
              and dy["reasons"][1]=="DynDOLOD.esp needs master(s) that are not enabled: Gone.esp"
              and dy["plugins"]==[{"plugin":"DynDOLOD.esp","missing_masters":["Gone.esp"],"plugins_loading_after":["Late.esp"]}])
        tg = by["Step - TexGen_Output"]
        check("TexGen: texture mod newer, hidden files and disabled mods ignored, DynDOLOD output not counted",
              [c["mod"] for c in tg["changed_mods"]]==["Tex Mod"] and tg["changed_mods"][0]["examples"]==["textures/rocks/rock.dds"])
        e,t = call("check_outputs", {"names":["step - texgen_output"]}); r=json.loads(t)
        check("plugin top-level groups are read", __import__("mo2_mcp.espm", fromlist=["x"]).read_plugin(
              os.path.join(org.modsPath(), "Quest Plugin", "Quest.esp")).top_groups == {"QUST"})
        check("check_outputs with a name checks just that mod", [x["mod"] for x in r["outputs"]]==["Step - TexGen_Output"])
        os.utime(os.path.join(org.modsPath(), "Tex Mod", "textures", "rocks", "rock.dds"), (T0 - 10, T0 - 10))
        os.utime(os.path.join(org.profilePath(), "modlist.txt"), (T0 - 10, T0 - 10))
        e,t = call("check_outputs", {"names":["Step - TexGen_Output"]}); r=json.loads(t)
        check("check_outputs: up to date", r["outputs"][0]["verdict"]=="up to date" and "changed_mods" not in r["outputs"][0])
        # -- Community Shaders --
        e,t = call("check_community_shaders"); r=json.loads(t)
        check("CS check without CS installed", not e and r["core"]["mod"] is None and r["features"]==[]
              and r["core"]["log"].startswith("not found"))
        add_mod("CS Old", {"SKSE/Plugins/CommunityShaders.dll": ("old", 0)}, active=False)
        add_mod("CS Core", {"SKSE/Plugins/CommunityShaders.dll": ("dll", 0),
                            "Shaders/Features/Alpha.ini": ("[Info]\nVersion = 1-2-0\n", 0),
                            "Shaders/Features/Beta.ini": ("[Info]\nVersion = 2-0-0\n", 0),
                            "Shaders/Features/Zed.ini": ("[Info]\nVersion = 0-1-0\n", 0)})
        add_mod("Beta Old", {"Shaders/Features/Beta.ini": ("[Info]\nVersion = 1-0-0\n", 0)})
        add_mod("Gamma", {"Shaders/Features/Gamma.ini": ("[Info]\nVersion = 1-0-0\n", 0)})
        os.makedirs(os.path.join(org.overwritePath(), "ShaderCache", "Lighting"), exist_ok=True)
        open(os.path.join(org.overwritePath(), "ShaderCache", "Lighting", "x.bin"), "w").close()
        with open(os.path.join(tmp, "docs", "SKSE", "CommunityShaders.log"), "w") as f:
            f.write("[12:51:51.197] [6896 ] [I] CommunityShaders v2-0-0-0\n"
                    "[12:51:51.197] [6896 ] [I] Community Shaders 2.0.0 | branch: dev\n"
                    "[12:51:51.263] [6896 ] [W] 5 old-format override file(s) in CommunityShaders/Overrides are not compatible anymore.\n"
                    "[12:51:51.282] [6896 ] [I] Alpha.ini 1-2-0 successfully loaded\n"
                    "[12:51:51.282] [6896 ] [I] Beta.ini 1-0-0 successfully loaded\n"
                    "[12:51:51.282] [6896 ] [I] Delta.ini failed to load, feature disabled\n"
                    "[12:51:51.300] [6896 ] [I] Feature 'Epsilon' is disabled at boot.\n"
                    "[12:51:51.300] [6896 ] [W] Zed 0-1-0 is an old feature version, required: 1-0-0\n")
        e,t = call("check_community_shaders"); r=json.loads(t)
        by = {x["feature"]: x for x in r["features"]}
        check("CS core DLL: winner and other copies",
              not e and r["core"]["mod"]=="CS Core" and r["core"]["log_version"]=="2-0-0-0"
              and [(c["mod"], c["mod_enabled"], c.get("wins", False)) for c in r["core"]["dll_copies"]]==[("CS Old",False,False),("CS Core",True,True)])
        check("CS features: versions, winners, override of the core's version",
              by["Alpha"]=={"feature":"Alpha","mod":"CS Core","version":"1-2-0","last_start":"loaded"}
              and by["Beta"]["mod"]=="Beta Old" and by["Beta"]["version"]=="1-0-0"
              and by["Beta"]["other_copies"]==[{"mod":"CS Core","version":"2-0-0"}] and "overrides the version" in by["Beta"]["problem"]
              and by["Gamma"]["last_start"].startswith("not in the log"))
        check("CS log statuses: not installed, disabled at boot, old version",
              by["Delta"]=={"feature":"Delta","last_start":"not installed"} and by["Epsilon"]["last_start"]=="disabled at boot"
              and by["Zed"]["last_start"]=="not loaded" and "old feature version" in by["Zed"]["problem"]
              and r["summary"]=={"features":6,"loaded_last_start":2,"problems":2}
              and r["log_warnings"][0].startswith("[W] 5 old-format override"))
        check("CS shader cache found in Overwrite", r["shader_cache"][0]["mod"]=="(Overwrite)" and r["shader_cache"][0]["files"]==1)
        e,t = call("check_community_shaders", {"problems_only":True})
        check("CS problems_only", sorted(x["feature"] for x in json.loads(t)["features"])==["Beta","Zed"])
        # -- tool logs --
        tools_dir = os.path.join(tmp, "tools")
        def put(rel, text, age=0):
            path = os.path.join(tools_dir, *rel.split("/")); os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f: f.write(text)
            t = time.time() - 1000 + age; os.utime(path, (t, t))
        put("DynDOLOD/DynDOLODx64.exe", "")
        put("DynDOLOD/Logs/DynDOLOD_SSE_log.txt", "DynDOLOD 3.0 starting session 2026-11-16 10:00:00\nold run line\n<Warning: old>\n"
            "DynDOLOD 3.0 starting session 2026-11-17 13:46:17\n[00:00] Using Data Path\n<Warning: Worldspace bounds larger>\n"
            "[27:55] Created a summary\n", 10)
        put("DynDOLOD/Logs/DynDOLOD_SSE_Debug_log.txt", "debug", 20)
        put("DynDOLOD/Summary/DynDOLOD_Summary_Index.html", "<html>")
        put("DynDOLOD/Summary/DynDOLOD_Summary_RootBlock.html", "<html>")
        put("DynDOLOD/bugreport.txt", "boom")
        put("xEdit/SSEEdit.exe", "")
        put("xEdit/SSEEditQuickAutoClean.exe", "")
        put("xEdit/SSEEdit_log.txt", "SSEEdit 4.1.5f (Quick Auto Clean) starting session 2026-11-15 11:15:11\n"
            "[Removing \"Identical to Master\" records done]  Processed Records: 4131, Removed Records: 15, Elapsed Time: 00:00\n"
            "[00:01] Saving: Some.esp.save.2026_11_15\n        itm: 15\nother line\n")
        with open(os.path.join(tmp, "ModOrganizer.ini"), "a") as f: pass
        cfg = open(os.path.join(tmp, "ModOrganizer.ini")).read()
        cfg = cfg.replace("size=2", "size=4") + (f"3\\title=DynDOLOD\n3\\binary={tools_dir}/DynDOLOD/DynDOLODx64.exe\n"
                                                 f"4\\title=QAC\n4\\binary={tools_dir}/xEdit/SSEEditQuickAutoClean.exe\n")
        with open(os.path.join(tmp, "ModOrganizer.ini"), "w") as f: f.write(cfg)
        e,t = call("read_log", {"log":"dyndolod"})
        check("read_log dyndolod: newest non-debug log, last session, summary and bugreport",
              not e and "DynDOLOD_SSE_log.txt" in t and "old run line" not in t and "Worldspace bounds" in t
              and "last of 2 sessions" in t and "Topics: RootBlock" in t and "bugreport.txt found" in t)
        e,t = call("read_log", {"log":"dyndolod", "session":False, "problems_only":True})
        check("read_log problems_only and all sessions", "<Warning: old>" in t and "Worldspace bounds" in t and "Using Data Path" not in t)
        e,t = call("read_log", {"log":"xedit"})
        check("read_log xedit: Quick Auto Clean highlights",
              not e and "What was cleaned and saved" in t and "Removed Records: 15" in t and "Saving: Some.esp" in t and "itm: 15" in t)
        e,t = call("read_log", {"log":"texgen"}); check("read_log texgen without executable", e and "No texgen executable" in t)
        e,t = call("read_log", {"log":"pandora"}); check("read_log pandora Engine.log from the output mod", not e and "Engine.log" in t and t.rstrip().endswith("ok"))
        e,t = call("read_log", {"log":"skse"}); r=json.loads(t)
        check("read_log skse lists logs", "CommunityShaders" in r["skse_logs"] and "skse64" in r["skse_logs"])
        e,t = call("read_log", {"log":"skse", "name":"communityshaders", "problems_only":True})
        check("read_log skse by name, problems only", not e and "old-format override" in t and "Zed 0-1-0" in t and "Alpha.ini" not in t)
        os.environ["LOCALAPPDATA"] = tmp; put("../LOOT/LOOTDebugLog.txt", "[info]: LOOT version: 0.29.2\n")
        e,t = call("read_log", {"log":"loot"}); check("read_log loot", not e and "LOOT version" in t)
        # -- LOOT --
        ldir = os.path.join(tmp, "LOOT", "games", "Skyrim Special Edition")
        os.makedirs(os.path.join(ldir, "backups"), exist_ok=True)
        with open(os.path.join(ldir, "old_messages.json"), "w") as f:
            json.dump({"messages": [{"text": "Your **SKSE** is up-to-date."},
                                    {"pluginName": "AsIs.esp", "text": "Read the [Compatibility Notes](https://x/y)."},
                                    {"pluginName": "NotInstalled.esp", "text": "ignored"}]}, f)
        with open(os.path.join(ldir, "backups", "loadorder.1.json"), "w") as f:
            json.dump({"loadOrder": ["Skyrim.esm", "Update.esm", "Big.esp", "EngineFixes.esp"]}, f)
        e,t = call("loot_sort", {"dry_run": True}); r=json.loads(t)
        check("loot_sort dry run: messages, last sort, nothing started",
              not e and r["executable"]=="LOOT" and r["would_run"]=="--auto-sort" and org.started[-1]!="LOOT2"
              and r["general_messages"]==["Your SKSE is up-to-date."]
              and r["plugin_messages"]=={"AsIs.esp":["Read the Compatibility Notes (https://x/y)."]}
              and r["last_sort"]["moved_since_then"]==[{"plugin":"EngineFixes.esp","from":3,"to":2}])
        started_before = len(org.started); seen_args = []
        real_start = org.startApplication
        def loot_start(exe, args=[], cwd=""):
            seen_args.append(list(args))
            order = org.pl.order; order.remove("Big.esp"); order.insert(3, "Big.esp")  # LOOT moves one plugin
            return real_start(exe, args, cwd)
        org.startApplication = loot_start
        e,t = call("loot_sort"); r=json.loads(t)
        check("loot_sort runs standalone LOOT with --auto-sort and lists what moved",
              not e and org.started[started_before:]==["LOOT"] and seen_args==[["--auto-sort"]]
              and r["run"]["status"]=="finished" and r["refreshed"] is True
              and r["moved"]==[{"plugin":"Big.esp","from":6,"to":3}]
              and r["summary"]=="1 plugin(s) moved" and "messages_note" in r)
        org.startApplication = real_start
        cache=json.loads(P.TOOLS_CACHE.read_text()); check("tools cache written", len(cache)==30)
    except Exception as ex:
        import traceback; traceback.print_exc(); failures.append(repr(ex))
    finally:
        QTimer.singleShot(0, app.quit)

threading.Thread(target=client, daemon=True).start()
app.exec()
plug.stop()
print("FAILURES:", failures); sys.exit(1 if failures else 0)

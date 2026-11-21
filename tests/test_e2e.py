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
    def __init__(s): s.order=["Skyrim.esm","Update.esm","EngineFixes.esp"]; s.st={p:mobase.PluginState.ACTIVE for p in s.order}
    def pluginNames(s): return list(s.order)
    def priority(s,n): return s.order.index(n)
    def loadOrder(s,n): return s.order.index(n) if s.st[n]==mobase.PluginState.ACTIVE else -1
    def state(s,n): return s.st[n]
    def setState(s,n,v): s.st[n]=v
    def setPriority(s,n,p): s.order.remove(n); s.order.insert(p,n); return True
    def isMasterFlagged(s,n): return n.endswith(".esm")
    def hasMasterExtension(s,n): return n.endswith(".esm")
    def isLightFlagged(s,n): return False
    def hasLightExtension(s,n): return False
    def isMediumFlagged(s,n): return False
    def hasNoRecords(s,n): return False
    def origin(s,n): return "data" if n.endswith(".esm") else "SSE Engine Fixes"

class Game:
    def gameName(s): return "Skyrim Special Edition"
    def gameVersion(s): return "1.6.1170"
    def gameDirectory(s):
        from PyQt6.QtCore import QDir; return QDir("/game")

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
        s.profile_name="Step"; s.manage_opened=False
        for prof in ("Step","Mod Dev"): os.makedirs(os.path.join(root,"profiles",prof),exist_ok=True); s.dm=DownloadManager(root)
        with open(os.path.join(root,"ModOrganizer.ini"),"w") as f:
            f.write("[customExecutables]\nsize=2\n1\\title=SSEEdit\n1\\binary=H:/Tools/SSEEdit/SSEEdit.exe\n1\\arguments=\n1\\workingDirectory=\n2\\title=LOOT\n2\\binary=H:/Tools/LOOT/LOOT.exe\n2\\arguments=\n2\\workingDirectory=\n")
    def modList(s): return s.ml
    def pluginList(s): return s.pl
    def managedGame(s): return Game()
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
    def resolvePath(s,p): return "/x/"+p
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
        check("tools/list has 25 tools", len(names)==25)
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
        cache=json.loads(P.TOOLS_CACHE.read_text()); check("tools cache written", len(cache)==25)
    except Exception as ex:
        import traceback; traceback.print_exc(); failures.append(repr(ex))
    finally:
        QTimer.singleShot(0, app.quit)

threading.Thread(target=client, daemon=True).start()
app.exec()
plug.stop()
print("FAILURES:", failures); sys.exit(1 if failures else 0)

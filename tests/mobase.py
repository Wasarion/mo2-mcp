"""Tiny runtime fake of mobase for tests."""
import enum
class ModState(enum.IntFlag):
    EXISTS=1; ACTIVE=2; ESSENTIAL=4; EMPTY=8; ENDORSED=16; VALID=32; ALTERNATE=64
class PluginState(enum.IntEnum):
    MISSING=0; INACTIVE=1; ACTIVE=2
class IPlugin:
    def __init__(self): pass
class VersionInfo:
    def __init__(self, s=""): self.s=s
    def displayString(self): return self.s
class PluginSetting:
    def __init__(self,k,d,v): self.key=k; self.default_value=v
class IOrganizer: pass
class GuessedString(str):
    pass

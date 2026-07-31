from pathlib import Path
p=Path('local/crates/fennara-daemon/tests/fixtures/fake_codex_app_server.py')
s=p.read_text(encoding='utf-8')
s=s.replace('    version: str = "0.0.0-fake"','    version: str = "0.144.4"\n    initialize_shape: str = "valid"',1)
old='''                {
                    "userAgent": f"codex/{self.scenario.version} fake-fixture",
                    "capabilities": {
                        "threadResume": True,
                        "accountLoginCancel": True,
                    },
                },
'''
new='''                self.initialize_result(),
'''
if 'self.initialize_result()' not in s:
    if s.count(old)!=1: raise RuntimeError('fixture initialize result')
    s=s.replace(old,new,1)
marker='''    def maybe_delay(self) -> None:
'''
helper='''    def initialize_result(self) -> dict[str, Any]:
        if sys.platform.startswith("win"):
            platform_os = "windows"
            platform_family = "windows"
        elif sys.platform == "darwin":
            platform_os = "macos"
            platform_family = "unix"
        else:
            platform_os = "linux"
            platform_family = "unix"
        result = {
            "userAgent": f"codex/{self.scenario.version} fake-fixture",
            "codexHome": os.environ.get("CODEX_HOME", str(Path.home() / ".codex")),
            "platformFamily": platform_family,
            "platformOs": platform_os,
        }
        if self.scenario.initialize_shape == "missing-platform":
            result.pop("platformOs")
        return result

'''
if 'def initialize_result(' not in s:
    if s.count(marker)!=1: raise RuntimeError('fixture method marker')
    s=s.replace(marker,helper+marker,1)
p.write_text(s,encoding='utf-8',newline='\n')

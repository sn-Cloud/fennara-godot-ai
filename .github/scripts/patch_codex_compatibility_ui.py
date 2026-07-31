from pathlib import Path
for relative in ['ui/chat/app.js','godot_demo/addons/fennara/dist/app.js']:
    p=Path(relative);s=p.read_text(encoding='utf-8')
    old='''        if (compatibility === "tested") {
          details.push("tested runtime");
        } else if (compatibility === "compatible_unverified") {
          details.push("unverified runtime");
        } else if (compatibility === "unknown") {
          details.push("unknown runtime");
        }
'''
    new='''        if (compatibility === "tested") {
          details.push("tested runtime");
        } else if (compatibility === "compatible_unverified") {
          details.push("unverified runtime");
        } else if (compatibility === "incompatible") {
          details.push("incompatible runtime");
        }
'''
    if 'details.push("incompatible runtime")' not in s:
        if s.count(old)!=1: raise RuntimeError(f'{relative}: compatibility UI block')
        s=s.replace(old,new,1)
    p.write_text(s,encoding='utf-8',newline='\n')

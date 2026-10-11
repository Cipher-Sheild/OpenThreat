"""Check a publication tree without printing suspected secret values."""
from pathlib import Path
import re,sys
root=Path(__file__).resolve().parents[1]
blocked={'.env','.env.local','.env.production'}
suffixes={'.db','.sqlite','.sqlite3','.dump','.sql','.pt','.pth','.safetensors','.bin','.onnx'}
bad_dirs={'node_modules','__pycache__','.venv','model_cache'}
patterns=[re.compile(p) for p in [r'gh[pousr]_[A-Za-z0-9]{30,}',r'github_pat_[A-Za-z0-9_]{30,}',r'hf_[A-Za-z0-9]{25,}',r'AKIA[A-Z0-9]{16}',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']]
issues=[]
for p in root.rglob('*'):
 if not p.is_file() or '.git' in p.relative_to(root).parts:continue
 rel=p.relative_to(root)
 if p.name in blocked or (p.name.startswith('.env') and p.name!='.env.example') or p.suffix in suffixes or any(d in bad_dirs for d in rel.parts):issues.append((rel,'excluded runtime/private file'));continue
 try:text=p.read_text(encoding='utf-8')
 except (UnicodeDecodeError,OSError):continue
 if any(rx.search(text) for rx in patterns):issues.append((rel,'possible credential'))
for rel,kind in issues:print(f'{kind}: {rel}')
if issues:sys.exit(1)
print('Publication check passed: no blocked runtime files or common credential patterns found.')

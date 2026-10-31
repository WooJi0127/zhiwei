"""Give JS/CSS content-based URLs so old browser caches cannot break new HTML."""
import hashlib
from pathlib import Path
import re


def stamp_assets(root):
    core=Path(root)/'core'
    page=core/'index.html'
    original=page.read_text(encoding='utf-8')
    text=original
    for name in ('app.css','app.js'):
        # Match sync.py's text inlining and Git's Windows/Linux newline conversion.
        content=(core/name).read_text(encoding='utf-8').encode('utf-8')
        version=hashlib.sha256(content).hexdigest()[:16]
        text,count=re.subn(r'((?:href|src)=")'+re.escape(name)+r'(?:\?[^"<>]*)?"',
            lambda m:m.group(1)+name+'?v='+version+'"',text)
        if count!=1:raise ValueError('Expected one asset reference: '+name)
    if text!=original:page.write_text(text,encoding='utf-8',newline='\n')


if __name__=='__main__':stamp_assets(Path(__file__).resolve().parents[1])

"""No-dependency static frontend sync for direct source development / offline builds.

Vite remains optional for HMR and optimized assets; running this script is enough
for the shipped plain JS/CSS frontend.
"""
from pathlib import Path
src=Path(__file__).parent/'frontend'
dst=Path(__file__).parent/'bookledger'/'frontend_dist'
dst.mkdir(parents=True,exist_ok=True)
html=(src/'index.html').read_text(encoding='utf-8')
html=html.replace('<script type="module" src="/src/main.js"></script>', '<script type="module" src="/main.js"></script>')
html=html.replace('</head>','<link rel="stylesheet" href="/style.css"></head>')
(dst/'index.html').write_text(html,encoding='utf-8')
js=(src/'src'/'main.js').read_text(encoding='utf-8').replace("import './style.css';",'')
(dst/'main.js').write_text(js,encoding='utf-8')
(dst/'advanced.js').write_text((src/'src'/'advanced.js').read_text(encoding='utf-8'),encoding='utf-8')
(dst/'style.css').write_text((src/'src'/'style.css').read_text(encoding='utf-8'),encoding='utf-8')
print('Synced static frontend to',dst)

import json,sys,traceback
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(REPO))
from igdm_digest.collect import collect_one
sel=json.load(open(sys.argv[1])); root=REPO/'data'/'연출 수집'
for f,items in sel.items():
    for it in items:
        try:
            p=collect_one(it,f,root); n=len(list(p.glob('cut_*.mp4'))); print('OK',f,it['code'],n,'cuts',flush=True)
        except Exception as e:
            print('FAIL',f,it['code'],repr(e)[:200],flush=True)

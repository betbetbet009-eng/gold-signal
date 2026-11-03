# รันเช็กสัญญาณวนทุก 2 นาทีต่อเนื่อง ~5 ชม. 40 นาที แล้วสั่งรอบใหม่ของตัวเอง
# (GitHub ตัดรอบ schedule ทิ้งบ่อย จึงใช้การวนเองแทนการพึ่ง cron)
import subprocess, sys, time, traceback

INTERVAL_SEC = 120
RUN_FOR_SEC = 5 * 3600 + 40 * 60


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def sync_and_save():
    sh("git add state.json paper.json")
    if sh("git diff --cached --quiet").returncode != 0:
        sh('git commit -q -m "update alert/demo state"')
        for _ in range(3):
            sh("git pull -q --rebase")
            if sh("git push -q").returncode == 0:
                return
            time.sleep(5)
    else:
        sh("git pull -q --rebase")


def main():
    sh('git config user.name "gold-bot"')
    sh('git config user.email "gold-bot@users.noreply.github.com"')
    import check_signal
    start = time.time()
    while time.time() - start < RUN_FOR_SEC:
        try:
            check_signal.main()
        except Exception:
            traceback.print_exc()
        sync_and_save()
        sys.stdout.flush()
        time.sleep(INTERVAL_SEC)
    r = sh("gh workflow run signal.yml --ref main")
    print("next run:", r.returncode, r.stdout, r.stderr)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

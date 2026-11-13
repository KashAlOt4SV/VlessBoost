"""Offline native-window smoke check, available with --self-check REPORT.json."""
def run(report_path):
    import json
    import time
    from pathlib import Path
    started = time.perf_counter()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from app.settings import Settings
    from app.ui.veil import VeilWindow

    class OfflineWindow(VeilWindow):
        def _initial_checks(self):
            pass

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = OfflineWindow(settings=Settings())
    window.show()
    app.processEvents()
    report = {"startup_window_ms": round((time.perf_counter()-started)*1000, 2)}
    import ssl
    from app.connection_check import tls_context
    context = tls_context()
    report["trusted_ca_count"] = context.cert_store_stats()["x509_ca"]
    report["tls_verification_required"] = context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    before = time.perf_counter()
    pages = [window.stack.widget(i) for i in range(4)]
    for i in range(80):
        window._navigate(i % 4)
        app.processEvents()
    report["navigation_80_total_ms"] = round((time.perf_counter()-before)*1000, 2)
    report["pages_reused"] = pages == [window.stack.widget(i) for i in range(4)]
    window._navigate(0)
    window.showMaximized()
    app.processEvents()
    restored = True
    for _ in range(10):
        window.showMinimized()
        app.processEvents()
        window._restore()
        app.processEvents()
        restored = restored and window.isMaximized() and not window.isMinimized()
    report["maximize_restore_10_cycles_ok"] = restored
    window.showNormal()
    app.processEvents()
    gaps = []
    last = time.perf_counter()
    timer = QTimer()
    timer.setInterval(16)
    def pulse():
        nonlocal last
        now = time.perf_counter()
        gaps.append((now-last)*1000)
        last = now
    timer.timeout.connect(pulse)
    timer.start()
    window._work(lambda: time.sleep(.4), lambda _: report.update(worker_completed=True))
    def finish():
        timer.stop()
        report["max_ui_tick_gap_ms"] = round(max(gaps, default=0), 2)
        report["event_loop_ticks_during_worker"] = len(gaps)
        output = Path(report_path).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(output.with_suffix(".png")))
        report["ok"] = bool(report["pages_reused"] and restored and report.get("worker_completed") and len(gaps) > 15
                            and report["trusted_ca_count"] > 0 and report["tls_verification_required"])
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        window._quit()
    QTimer.singleShot(650, finish)
    app.exec()
    return 0 if report.get("ok") else 1

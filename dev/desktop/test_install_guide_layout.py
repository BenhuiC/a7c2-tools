from PySide6 import QtCore, QtGui, QtTest, QtWidgets


def test_custom_looks_expand_the_install_guide_scroll_content(monkeypatch, tmp_path):
    from desktopapp import window

    monkeypatch.setenv('A7C2_DESKTOP_DATA', str(tmp_path))
    monkeypatch.setattr(window, 'load_settings', lambda: {})
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    view = window.Window(demo=True)
    view.timer.stop()
    try:
        guide = view.install_guide
        guide.go(guide.steps.count() - 3)
        view.resize(1180, 890)
        view.show()
        view.local_custom_looks.setChecked(True)
        app.processEvents()
        scroll = view.page_widgets['install']
        editor = view.firmware_look_editor

        def assert_reachable(widget):
            scroll.ensureWidgetVisible(widget, 0, 0)
            app.processEvents()
            assert QtGui.QRegion(widget.rect()).subtracted(widget.visibleRegion()).isEmpty()

        for count in range(1, 7):
            editor.add.click()
            for _ in range(4):
                app.processEvents()
            assert len(editor.rows) == count
            for widget in (editor.rows[-1], guide.build_button, guide.next):
                assert_reachable(widget)

        notice = view.firmware_config_notice
        feature_card = view.local_ssh.parentWidget()
        for width, height in ((1000, 740), (1180, 890)):
            view.resize(width, height)
            QtTest.QTest.qWait(30)
            assert notice.geometry().top() > feature_card.geometry().bottom()
            assert_reachable(editor.rows[-1])
            assert_reachable(guide.build_button)

        full_range = scroll.verticalScrollBar().maximum()
        guide.next.click()
        app.processEvents()
        assert scroll.verticalScrollBar().maximum() < full_range
        guide.back.click()
        app.processEvents()
        assert_reachable(editor.rows[-1])

        for row in editor.rows[2:]:
            editor.remove_row(row)
        QtTest.QTest.qWait(30)
        assert len(editor.rows) == 2
        assert scroll.verticalScrollBar().maximum() < full_range
        assert_reachable(guide.build_button)
    finally:
        view.close()
        view.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)

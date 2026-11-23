"""Compact installation guide sharing the original driver and firmware panels."""
from copy import deepcopy
from pathlib import Path
import sys
from PySide6 import QtCore,QtWidgets as W


class StepStack(W.QWidget):
    """Only the visible page participates in the content layout."""
    def __init__(self):
        super().__init__();self._pages=[];self._index=0
        layout=W.QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0);layout.setAlignment(QtCore.Qt.AlignTop)

    def addWidget(self,page):
        self.layout().addWidget(page);self._pages.append(page)
        page.setVisible(len(self._pages)==1)

    def widget(self,index):return self._pages[index]
    def count(self):return len(self._pages)
    def currentIndex(self):return self._index
    def currentWidget(self):return self._pages[self._index]if self._pages else None

    def setCurrentIndex(self,index):
        self._index=index
        for i,page in enumerate(self._pages):page.setVisible(i==index)
        self.layout().invalidate();self.updateGeometry()


class InstallGuide(W.QWidget):
    def __init__(self,window):
        super().__init__();self.window=window
        self.pending=None;self.pending_args=None;self.built=None
        self.configured=False;self.bound=False;self.panels=[]
        self.setSizePolicy(W.QSizePolicy.Preferred,W.QSizePolicy.Maximum)
        outer=W.QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.setSpacing(10)
        outer.setAlignment(QtCore.Qt.AlignTop)
        self.progress=W.QLabel();self.progress.setProperty('section',True)
        outer.addWidget(self.progress)
        self.steps=StepStack();self.steps.setSizePolicy(W.QSizePolicy.Preferred,W.QSizePolicy.Maximum)
        outer.addWidget(self.steps)
        self.driver_pane=None;self.driver_status=None;self.driver_button=None
        if sys.platform!='darwin':
            self.driver_pane=self.pane()
            self.driver_status=self.note(self.driver_pane,'');self.driver_status.hide()
        self.firmware_pane=self.pane()
        self.build_status=self.note(self.firmware_pane,'');self.build_status.hide()
        p=self.pane('首次授信','第一次安装时，通过 USB 安装机身公钥；已有授信可直接下一步。软件会自动保留原始备份。')
        self.trust_status=self.note(p,'已授信可跳过；需要时可再次安装公钥。')
        self.trust_button=self.button(p,'通过 USB 安装机身公钥',lambda:self.run('firmware_trust_install',dict(workspace=window.work('trust-install'))),True)
        self.trust_restore_button=self.button(p,'恢复授信（恢复原厂公钥）',window.restore_trust)
        p=self.pane('写入配置，然后手动卡刷','确认 SD 卡已装入相机，卡根目录已有本次生成的 BODYDATA.DAT。')
        self.config_summary=self.note(p,'')
        self.config_button=self.button(p,'通过 USB 写入本次功能配置',lambda:self.run('firmware_settings_install',window.feature_settings_args()),True)
        self.card_instructions=self.note(p,'写完配置 → 拔 USB → 保持开机 → 在相机菜单执行固件更新。\n卡刷前不要关机或取电池；如果中途重启，请重新写配置。')
        self.card_instructions.setProperty('callout',True)
        self.config_status=self.note(p,'尚未写入配置。')
        navigation=W.QHBoxLayout();navigation.setProperty('fill',True);navigation.setSpacing(8)
        self.back=self.button(navigation,'上一步',lambda:self.go(self.steps.currentIndex()-1))
        navigation.addStretch()
        self.next=self.button(navigation,'下一步',lambda:self.go((self.steps.currentIndex()+1)%self.steps.count()),True)
        outer.addLayout(navigation)
        self.go(0)

    def pane(self,title=None,detail=None):
        page=W.QWidget();layout=W.QVBoxLayout(page)
        layout.setContentsMargins(0,6,0,0);layout.setSpacing(8)
        layout.setAlignment(QtCore.Qt.AlignTop)
        if title:
            heading=W.QLabel(title);heading.setProperty('section',True);layout.addWidget(heading)
        if detail:self.note(layout,detail)
        self.steps.addWidget(page);return layout

    def note(self,layout,text):
        label=W.QLabel(text);label.setWordWrap(True);layout.addWidget(label);return label

    def button(self,layout,text,callback,primary=False):
        button=W.QPushButton(text);button.setProperty('primary',primary)
        button.clicked.connect(callback);layout.addWidget(button)
        return button

    def bind(self):
        v=self.window
        # Reparent the existing widgets; fields, actions and sidebar remain shared.
        for index,host in (('drivers',self.driver_pane),('firmware',self.firmware_pane)):
            if host is None:continue
            home=v.page_widgets[index].widget().layout()
            column=home.itemAt(0).widget()
            placeholder=W.QWidget();W.QVBoxLayout(placeholder)
            self.panels.append((home,host,column,placeholder))
        if self.driver_pane is not None:
            self.driver_button=v.page_widgets['drivers'].findChild(W.QPushButton,'action_usb_prepare')
        self.build_button=v.page_widgets['firmware'].findChild(W.QPushButton,'action_firmware_build')
        for button,action,args in ((self.driver_button,'usb_prepare',v.common),
                                  (self.build_button,'firmware_build',v.firmware_args)):
            if button is None:continue
            button.clicked.disconnect()
            button.clicked.connect(lambda _checked=False,a=action,f=args:self.run_original(a,f))
        for name in ('fl23','wb','sound','looks','vertical','ssh'):
            getattr(v,'local_'+name).toggled.connect(self.refresh)
        v.local_presets.toggled.connect(self.refresh)
        for key in ('firmware_source','firmware_output','firmware_update_version'):
            v.fields[key].textChanged.connect(self.refresh)
        v.firmware_look_editor.changed.connect(self.refresh)
        for control in (v.local_custom_sound,v.firmware_sound_electronic,v.firmware_sound_mechanical):
            control.toggled.connect(self.refresh)
        v.fields['firmware_sound_source'].textChanged.connect(self.refresh)
        v.firmware_sound_start.valueChanged.connect(self.refresh)
        v.firmware_sound_duration.valueChanged.connect(self.refresh)
        self.bound=True;self.refresh()

    def mount(self,in_guide):
        for home,host,column,placeholder in self.panels:
            if in_guide and column.parentWidget() is not host.parentWidget():
                item=home.replaceWidget(column,placeholder)
                del item
                host.insertWidget(0,column);column.show()
            elif not in_guide and column.parentWidget() is host.parentWidget():
                host.removeWidget(column)
                item=home.replaceWidget(placeholder,column)
                del item
                placeholder.hide();column.show()
        self.steps.updateGeometry();self.updateGeometry()

    def options(self):
        try:return self.window.firmware_args()
        except (ValueError,OSError):return None

    def run_original(self,action,arguments):
        try:args=arguments()
        except (ValueError,OSError)as error:
            W.QMessageBox.information(self,'请检查生成选项',str(error));return
        if self.window.pages.currentWidget() is self.window.page_widgets['install']:self.run(action,args)
        else:self.window.launch(action,args)

    def run(self,action,args):
        if action=='firmware_build':self.built=None;self.configured=False
        elif action=='firmware_settings_install':self.configured=False
        self.pending=action;self.pending_args=deepcopy(args)
        if not self.window.launch(action,args):self.pending=None;self.pending_args=None
        self.refresh()

    def go(self,index):
        index=max(0,min(self.steps.count()-1,index))
        self.steps.setCurrentIndex(index)
        for i in range(self.steps.count()):
            self.steps.widget(i).setSizePolicy(W.QSizePolicy.Preferred,
                W.QSizePolicy.Preferred if i==index else W.QSizePolicy.Ignored)
        self.progress.setText('第 %d 步 / 共 %d 步'%(index+1,self.steps.count()))
        self.back.setVisible(index>0)
        self.next.setText('返回第一步' if index==self.steps.count()-1 else '下一步')
        self.steps.layout().invalidate();self.steps.updateGeometry()
        self.layout().invalidate();self.updateGeometry();self.refresh()

    def refresh(self,*_):
        if not self.bound:return
        v=self.window;idle=v.process is None
        if self.built and (self.built.get('options')!=self.options() or not Path(self.built.get('path','')).is_file()):
            self.built=None;self.configured=False
            self.build_status.setText('文件或选项已改变，实际安装前请重新生成固件。');self.build_status.show()
            self.config_status.setText('生成内容已改变，实际卡刷前请重新生成并写配置。')
        # Preview navigation has no completion or device prerequisites.
        self.back.setEnabled(True);self.next.setEnabled(True)
        self.trust_button.setEnabled(idle and v.trust_install_button.isEnabled())
        self.trust_restore_button.setEnabled(idle)
        self.config_button.setEnabled(idle)
        self.config_summary.setText('本次配置：'+('FL2／FL3、'if v.config_fl23.isChecked()else'')+('竖屏显示、'if v.config_vertical.isChecked()else'')+'关闭语音指南。')

    def finished(self,status,success):
        if self.pending is None or status.get('action')!=self.pending:return
        action=self.pending;args=self.pending_args;self.pending=None;self.pending_args=None
        result=status.get('result',{})
        label={'usb_prepare':self.driver_status,'firmware_build':self.build_status,
               'firmware_trust_install':self.trust_status,'firmware_settings_install':self.config_status}.get(action)
        if label:label.show()
        if not success:
            if label:label.setText('此步骤未完成，请查看下方日志。')
        elif action=='usb_prepare'and self.driver_status is not None:self.driver_status.setText('连接检查完成。按弹窗重开相机并接回 USB 后，再继续。')
        elif action=='firmware_build'and result.get('signed')and result.get('candidate'):
            self.built=dict(path=result['candidate'],options=args);self.configured=False
            self.build_status.setText('固件已保存至：'+result['candidate']+'。继续首次授信或写入配置。')
        elif action=='firmware_trust_install':
            self.trust_status.setText('公钥已写入并读回。继续写配置，随后直接卡刷。')
        elif action=='firmware_settings_install'and result.get('phase')=='SETTINGS_PREPARED_FOR_CARD':
            self.configured=True
            self.config_status.setText('配置已保存。拔 USB，保持开机，直接在相机菜单卡刷；重启后须重写配置。')
        self.window.select_page('install');self.refresh()

import os
import hal, hal_glib
import linuxcnc
from connections import Connections
from joypad import JoyPad
from facing import Facing
from hole_circle import Hole_Circle
from PyQt5 import QtCore, QtWidgets, QtGui, uic
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebEngineWidgets import QWebEnginePage
from qtvcp.widgets.gcode_editor import GcodeEditor as GCODE
from qtvcp.widgets.mdi_history import MDIHistory as MDI_WIDGET
from qtvcp.widgets.tool_offsetview import ToolOffsetView as TOOL_TABLE
from qtvcp.widgets.origin_offsetview import OriginOffsetView as OFFSET_VIEW
from qtvcp.widgets.stylesheeteditor import  StyleSheetEditor as SSE
from qtvcp.widgets.file_manager import FileManager as FM
from qtvcp.lib.keybindings import Keylookup
from qtvcp.lib.gcodes import GCodes
from qtvcp.core import Status, Action, Info, Path
from qtvcp import logger
from shutil import copyfile

LOG = logger.getLogger(__name__)
KEYBIND = Keylookup()
STATUS = Status()
INFO = Info()
ACTION = Action()
PATH = Path()
SUBPROGRAM = os.path.join(PATH.CONFIGPATH, 'qtdragon/touchoff_subprog.py')

# constants for tab pages
TAB_MAIN = 0
TAB_FILE = 1
TAB_OFFSETS = 2
TAB_TOOL = 3
TAB_STATUS = 4
TAB_PROBE = 5
TAB_CAMVIEW = 6
TAB_GCODES = 7
TAB_SETUP = 8
TAB_UTILS = 9
TAB_SETTINGS = 10

# this class provides an overloaded function to disable navigation links
class WebPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, navtype, mainframe):
        if navtype == self.NavigationTypeLinkClicked: return False
        return super().acceptNavigationRequest(url, navtype, mainframe)


class HandlerClass:
    def __init__(self, halcomp, widgets, paths):
        self.h = halcomp
        self.w = widgets
        self.gcodes = GCodes(widgets)
        self.valid = QtGui.QDoubleValidator(-999.999, 999.999, 3)
        self.styleeditor = SSE(widgets, paths)
        KEYBIND.add_call('Key_F4', 'on_keycall_F4')
        KEYBIND.add_call('Key_F12','on_keycall_F12')
        KEYBIND.add_call('Key_Pause', 'on_keycall_PAUSE')
        KEYBIND.add_call('Key_Any', 'on_keycall_PAUSE')
        # some global variables
        self.proc = None
        self.probe = None
        self.progress = None
        self.pause_dialog = None
        self.factor = 1.0
        self.jog_az = JoyPad()
        self.jog_xy = JoyPad()
        self.pgm_control = JoyPad()
        self.run_color = QtGui.QColor('green')
        self.stop_color = QtGui.QColor('red')
        self.pause_color = QtGui.QColor('yellow')
        self.default_setup = os.path.join(PATH.CONFIGPATH, "default_setup.html")
        self.start_line = 0
        self.run_time = 0
        self.time_tenths = 0
        self.timer_on = False
        self.home_all = False
        self.min_spindle_rpm = INFO.MIN_SPINDLE_SPEED
        self.max_spindle_rpm = INFO.MAX_SPINDLE_SPEED
        self.max_spindle_power = INFO.get_error_safe_setting('DISPLAY', 'MAX_SPINDLE_POWER',"0")
        self.max_linear_velocity = INFO.MAX_TRAJ_VELOCITY
        self.axis_list = INFO.AVAILABLE_AXES
        self.system_list = ["G54","G55","G56","G57","G58","G59","G59.1","G59.2","G59.3"]
        self.slow_jog_factor = 10
        self.reload_tool = 0
        self.last_loaded_program = ""
        self.first_turnon = True
        self.icon_btns = {'action_exit': 'SP_BrowserStop',
                          'btn_load_file': 'SP_DialogOpenButton'}

        self.unit_label_list = ["zoffset_units", "max_probe_units"]
        self.unit_speed_list = ["search_vel_units", "probe_vel_units"]

        self.lineedit_list = ["work_height", "touch_height", "sensor_height", "laser_x", "laser_y",
                              "sensor_x", "sensor_y", "camera_x", "camera_y",
                              "search_vel", "probe_vel", "max_probe", "eoffset_count"]

        self.onoff_list = ["program", "tool", "touchoff", "dro", "overrides", "feedrate", "spindle"]

        self.axis_a_list = ["widget_angular_jog", "widget_increments_angular", "dro_axis_a",
                            "axistoolbutton_a", "btn_zero_a", "btn_goto_zero_a"]

        STATUS.connect('general', self.dialog_return)
        STATUS.connect('state-on', lambda w: self.enable_onoff(True))
        STATUS.connect('state-off', lambda w: self.enable_onoff(False))
        STATUS.connect('mode-manual', lambda w: self.enable_auto(False))
        STATUS.connect('mode-mdi', lambda w: self.enable_auto(False))
        STATUS.connect('mode-auto', lambda w: self.enable_auto(True))
        STATUS.connect('gcode-line-selected', lambda w, line: self.set_start_line(line))
        STATUS.connect('hard-limits-tripped', self.hard_limit_tripped)
        STATUS.connect('user-system-changed', lambda w, data: self.user_system_changed(data))
        STATUS.connect('metric-mode-changed', lambda w, mode: self.metric_mode_changed(mode))
        STATUS.connect('current-feed-rate', lambda w, rate: self.w.gauge_feedrate.update_value(rate))
        STATUS.connect('command-stopped', self.command_stopped)
        STATUS.connect('file-loaded', lambda w, filename: self.file_loaded(filename))
        STATUS.connect('homed', self.homed)
        STATUS.connect('all-homed', self.all_homed)
        STATUS.connect('not-all-homed', self.not_all_homed)
        STATUS.connect('periodic', lambda w: self.update_status())
        STATUS.connect('interp-idle', lambda w: self.stop_timer())

    def class_patch__(self):
        self.old_fman = FM.load
        FM.load = self.load_code

    def initialized__(self):
        self.init_pins()
        self.init_preferences()
        self.init_widgets()
        self.init_probe()
        self.init_utils()
        self.init_joypads()
        self.w.stackedWidget_gcode.setCurrentIndex(0)
        self.w.stackedWidget_log.setCurrentIndex(0)
        self.w.btn_dimensions.setChecked(True)
        self.w.btn_tool_sensor.setEnabled(self.w.chk_use_tool_sensor.isChecked())
        self.w.page_buttonGroup.buttonClicked.connect(self.main_tab_changed)
        self.w.scale_buttonGroup.buttonClicked.connect(self.mpg_scale_changed)
        self.w.filemanager.onUserClicked()
        self.w.filemanager_usb.onMediaClicked()
        self.chk_use_tool_sensor_changed(self.w.chk_use_tool_sensor.isChecked())
        self.chk_use_touchplate_changed(self.w.chk_use_touchplate.isChecked())
        self.chk_use_mpg_changed(self.w.chk_use_mpg.isChecked())
        self.chk_run_from_line_changed(self.w.chk_run_from_line.isChecked())
        self.chk_use_camera_changed(self.w.chk_use_camera.isChecked())
        # hide widgets for A axis if not present
        if "A" not in self.axis_list:
            for i in self.axis_a_list:
                self.w[i].setEnabled(False)
        # set validators for lineEdit widgets
        for val in self.lineedit_list:
            self.w['lineEdit_' + val].setValidator(self.valid)
        # check for default setup html file
        try:
            url = QtCore.QUrl("file:///" + self.default_setup)
            self.web_view.load(url)
        except Exception as e:
            print("No default setup file found - {}".format(e))
        # set unit labels according to machine mode
        unit = "MM" if INFO.MACHINE_IS_METRIC else "IN"
        for i in self.unit_label_list:
            self.w['lbl_' + i].setText(unit)
        for i in self.unit_speed_list:
            self.w['lbl_' + i].setText(unit + "/MIN")
        self.w.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        # connect all signals to corresponding slots
        connect = Connections(self, self.w)

    #############################
    # SPECIAL FUNCTIONS SECTION #
    #############################
    def init_pins(self):
        # spindle control pins
        self.spindle_amps = self.h.newpin("spindle_amps", hal.HAL_FLOAT, hal.HAL_IN)
        self.spindle_volts = self.h.newpin("spindle_volts", hal.HAL_FLOAT, hal.HAL_IN)
        self.spindle_fault = self.h.newpin("spindle_fault", hal.HAL_U32, hal.HAL_IN)
        self.modbus_errors = self.h.newpin("modbus-errors", hal.HAL_U32, hal.HAL_IN)
        self.spindle_inhibit = self.h.newpin("spindle_inhibit", hal.HAL_BIT, hal.HAL_OUT)
        self.spindle_amps.value_changed.connect(lambda val: self.spindle_pwr_changed(val))
        self.spindle_volts.value_changed.connect(lambda val: self.spindle_pwr_changed(val))
        self.spindle_fault.value_changed.connect(lambda val: self.w.lbl_spindle_fault.setText(hex(val)))
        self.modbus_errors.value_changed.connect(lambda val: self.w.lbl_mb_errors.setText(str(val)))
        # external offset control pins
        self.eoffset_clear = self.h.newpin("eoffset_clear", hal.HAL_BIT, hal.HAL_OUT)
        self.eoffset_count = self.h.newpin("eoffset_count", hal.HAL_S32, hal.HAL_OUT)
        self.eoffset_value = self.h.newpin("eoffset_value", hal.HAL_FLOAT, hal.HAL_IN)
        # MPG axis select pins
        self.axis_select_x = self.h.newpin("axis_select_x", hal.HAL_BIT, hal.HAL_IN)
        self.axis_select_y = self.h.newpin("axis_select_y", hal.HAL_BIT, hal.HAL_IN)
        self.axis_select_z = self.h.newpin("axis_select_z", hal.HAL_BIT, hal.HAL_IN)
        self.axis_select_a = self.h.newpin("axis_select_a", hal.HAL_BIT, hal.HAL_IN)
        self.axis_select_x.value_changed.connect(self.show_selected_axis)
        self.axis_select_y.value_changed.connect(self.show_selected_axis)
        self.axis_select_z.value_changed.connect(self.show_selected_axis)
        self.axis_select_a.value_changed.connect(self.show_selected_axis)
        # MPG scale select pins
        self.scale_select_0 = self.h.newpin("scale_select_0", hal.HAL_BIT, hal.HAL_OUT)
        self.scale_select_1 = self.h.newpin("scale_select_1", hal.HAL_BIT, hal.HAL_OUT)
        
    def init_preferences(self):
        if not self.w.PREFS_:
            self.add_status("CRITICAL - no preference file found, enable preferences in screenoptions widget")
            return
        self.last_loaded_program = self.w.PREFS_.getpref('last_loaded_file', None, str,'BOOK_KEEPING')
        self.reload_tool = self.w.PREFS_.getpref('Tool to load', 0, int,'CUSTOM_FORM_ENTRIES')
        self.w.lineEdit_laser_x.setText(str(self.w.PREFS_.getpref('Laser X', 100, float, 'CUSTOM_FORM_ENTRIES')))
        self.w.lineEdit_laser_y.setText(str(self.w.PREFS_.getpref('Laser Y', -20, float, 'CUSTOM_FORM_ENTRIES')))
        self.w.lineEdit_sensor_x.setText(str(self.w.PREFS_.getpref('Sensor X', 10, float, 'CUSTOM_FORM_ENTRIES')))
        self.w.lineEdit_sensor_y.setText(str(self.w.PREFS_.getpref('Sensor Y', 10, float, 'CUSTOM_FORM_ENTRIES')))
        self.w.lineEdit_camera_x.setText(str(self.w.PREFS_.getpref('Camera X', 10, float, 'CUSTOM_FORM_ENTRIES')))
        self.w.lineEdit_camera_y.setText(str(self.w.PREFS_.getpref('Camera Y', 10, float, 'CUSTOM_FORM_ENTRIES')))
        self.w.lineEdit_work_height.setText(str(self.w.PREFS_.getpref('Work Height', 20, float, 'CUSTOM_FORM_ENTRIES')))
        self.w.lineEdit_touch_height.setText(str(self.w.PREFS_.getpref('Touch Height', 40, float, 'CUSTOM_FORM_ENTRIES')))
        self.w.lineEdit_sensor_height.setText(str(self.w.PREFS_.getpref('Sensor Height', 40, float, 'CUSTOM_FORM_ENTRIES')))
        self.w.lineEdit_search_vel.setText(str(self.w.PREFS_.getpref('Search Velocity', 40, float, 'CUSTOM_FORM_ENTRIES')))
        self.w.lineEdit_probe_vel.setText(str(self.w.PREFS_.getpref('Probe Velocity', 10, float, 'CUSTOM_FORM_ENTRIES')))
        self.w.lineEdit_max_probe.setText(str(self.w.PREFS_.getpref('Max Probe', 10, float, 'CUSTOM_FORM_ENTRIES')))
        self.w.lineEdit_eoffset_count.setText(str(self.w.PREFS_.getpref('Eoffset count', 0, int, 'CUSTOM_FORM_ENTRIES')))
        self.w.chk_reload_program.setChecked(self.w.PREFS_.getpref('Reload program', False, bool,'CUSTOM_FORM_ENTRIES'))
        self.w.chk_reload_tool.setChecked(self.w.PREFS_.getpref('Reload tool', False, bool,'CUSTOM_FORM_ENTRIES'))
        self.w.chk_use_keyboard.setChecked(self.w.PREFS_.getpref('Use keyboard', False, bool, 'CUSTOM_FORM_ENTRIES'))
        self.w.chk_use_tool_sensor.setChecked(self.w.PREFS_.getpref('Use tool sensor', False, bool, 'CUSTOM_FORM_ENTRIES'))
        self.w.chk_use_touchplate.setChecked(self.w.PREFS_.getpref('Use tool touchplate', False, bool, 'CUSTOM_FORM_ENTRIES'))
        self.w.chk_run_from_line.setChecked(self.w.PREFS_.getpref('Run from line', False, bool, 'CUSTOM_FORM_ENTRIES'))
        self.w.chk_use_camera.setChecked(self.w.PREFS_.getpref('Use camera', False, bool, 'CUSTOM_FORM_ENTRIES'))
        self.w.chk_use_mpg.setChecked(self.w.PREFS_.getpref('Use MPG jog', False, bool, 'CUSTOM_FORM_ENTRIES'))
        
    def closing_cleanup__(self):
        if not self.w.PREFS_: return
        self.w.PREFS_.putpref('last_loaded_directory', os.path.dirname(self.last_loaded_program), str, 'BOOK_KEEPING')
        self.w.PREFS_.putpref('last_loaded_file', self.last_loaded_program, str, 'BOOK_KEEPING')
        self.w.PREFS_.putpref('Tool to load', STATUS.get_current_tool(), int, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Laser X', self.w.lineEdit_laser_x.text(), float, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Laser Y', self.w.lineEdit_laser_y.text(), float, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Sensor X', self.w.lineEdit_sensor_x.text(), float, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Sensor Y', self.w.lineEdit_sensor_y.text(), float, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Camera X', self.w.lineEdit_camera_x.text(), float, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Camera Y', self.w.lineEdit_camera_y.text(), float, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Work Height', self.w.lineEdit_work_height.text(), float, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Touch Height', self.w.lineEdit_touch_height.text(), float, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Sensor Height', self.w.lineEdit_sensor_height.text(), float, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Search Velocity', self.w.lineEdit_search_vel.text(), float, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Probe Velocity', self.w.lineEdit_probe_vel.text(), float, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Max Probe', self.w.lineEdit_max_probe.text(), float, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Eoffset count', self.w.lineEdit_eoffset_count.text(), int, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Reload program', self.w.chk_reload_program.isChecked(), bool, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Reload tool', self.w.chk_reload_tool.isChecked(), bool, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Use keyboard', self.w.chk_use_keyboard.isChecked(), bool, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Use tool sensor', self.w.chk_use_tool_sensor.isChecked(), bool, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Use tool touchplate', self.w.chk_use_touchplate.isChecked(), bool, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Run from line', self.w.chk_run_from_line.isChecked(), bool, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Use camera', self.w.chk_use_camera.isChecked(), bool, 'CUSTOM_FORM_ENTRIES')
        self.w.PREFS_.putpref('Use MPG jog', self.w.chk_use_mpg.isChecked(), bool, 'CUSTOM_FORM_ENTRIES')
        if self.probe:
            self.probe.closing_cleanup__()

    def init_widgets(self):
        self.w.main_tab_widget.setCurrentIndex(0)
        self.w.adj_angular_jog.setValue(INFO.DEFAULT_ANGULAR_JOG_VEL)
        self.w.adj_spindle_ovr.setValue(100)
        self.w.chk_override_limits.setChecked(False)
        self.w.chk_override_limits.setEnabled(False)
        self.w.lbl_home_x.setText(INFO.get_error_safe_setting('JOINT_0', 'HOME',"50"))
        self.w.lbl_home_y.setText(INFO.get_error_safe_setting('JOINT_1', 'HOME',"50"))
        # gcode file history
        self.w.cmb_gcode_history.addItem("No File Loaded")
        self.w.cmb_gcode_history.view().setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        # mdi history
        self.w.mdihistory.MDILine.setFixedHeight(30)
        self.w.mdihistory.MDILine.setPlaceholderText('MDI:')
        # set calculator mode for menu buttons
        for i in ("x", "y", "z", "a"):
            self.w["axistoolbutton_" + i].set_dialog_code('CALCULATOR')
        # disable mouse wheel events on comboboxes
        self.w.cmb_gcode_history.wheelEvent = lambda event: None
        self.w.cmb_stylesheet.wheelEvent = lambda event: None
        self.w.jogincrements_linear.wheelEvent = lambda event: None
        self.w.jogincrements_angular.wheelEvent = lambda event: None
        self.w.gcode_editor.hide()
        # turn off table grids
        self.w.filemanager.table.setShowGrid(False)
        self.w.filemanager_usb.table.setShowGrid(False)
        self.w.tooloffsetview.setShowGrid(False)
        self.w.offset_table.setShowGrid(False)
        # move clock and runtimer to statusbar
        self.w.statusbar.addPermanentWidget(self.w.lbl_clock)
        #set up gcode list
        self.gcodes.setup_list()
        # set up web page viewer
        self.web_view = QWebEngineView()
        self.web_page = WebPage()
        self.web_view.setPage(self.web_page)
        self.w.layout_setup.addWidget(self.web_view)
        # initialize gauges
        self.w.gauge_feedrate._value_font_size = 12
        self.w.gauge_feedrate._label_font_size = 8
        self.w.gauge_feedrate.set_threshold(self.max_linear_velocity)
        self.w.gauge_spindle._value_font_size = 12
        self.w.gauge_spindle.set_threshold(self.max_spindle_rpm)
        # apply standard button icons
        for key in self.icon_btns:
            style = self.w[key].style()
            icon = style.standardIcon(getattr(QtWidgets.QStyle, self.icon_btns[key]))
            self.w[key].setIcon(icon)
        # populate stylesheet combobox - basically a copy of styleeditor combobox
        for i in range(self.styleeditor.styleSheetCombo.count()):
            item = self.styleeditor.styleSheetCombo.itemText(i)
            self.w.cmb_stylesheet.addItem(item)

    def init_probe(self):
        probe = INFO.get_error_safe_setting('PROBE', 'USE_PROBE', 'none').lower()
        if probe == 'versaprobe':
            LOG.info("Using Versa Probe")
            from qtvcp.widgets.versa_probe import VersaProbe
            self.probe = VersaProbe()
            self.probe.setObjectName('versaprobe')
        elif probe == 'basicprobe':
            LOG.info("Using Basic Probe")
            from qtvcp.widgets.basic_probe import BasicProbe
            self.probe = BasicProbe()
            self.probe.setObjectName('basicprobe')
        else:
            LOG.info("No valid probe widget specified")
            self.w.btn_probe.hide()
            return
        self.w.probe_layout.addWidget(self.probe)
        self.probe.hal_init()

    def init_utils(self):
        self.facing = Facing()
        self.w.layout_facing.addWidget(self.facing)
        self.hole_circle = Hole_Circle()
        self.w.layout_hole_circle.addWidget(self.hole_circle)

    def init_joypads(self):
        # jog A and Z
        self.w.layout_jog_buttons.addWidget(self.jog_az)
        if 'A' in self.axis_list:
            self.jog_az.set_icon('L', 'text', 'A-')
            self.jog_az.set_icon('R', 'text', 'A+')
        if 'Z' in self.axis_list:
            self.jog_az.set_icon('T', 'text', 'Z+')
            self.jog_az.set_icon('B', 'text', 'Z-')
        self.jog_az.joy_btn_clicked.connect(self.jog_az_clicked)
        self.jog_az.joy_btn_released.connect(self.jog_az_released)
        # jog X and Y
        self.w.layout_jog_buttons.addWidget(self.jog_xy)
        if 'X' in self.axis_list:
            self.jog_xy.set_icon('L', 'text', 'X-')
            self.jog_xy.set_icon('R', 'text', 'X+')
        if 'Y' in self.axis_list:
            self.jog_xy.set_icon('T', 'text', 'Y+')
            self.jog_xy.set_icon('B', 'text', 'Y-')
        self.jog_xy.joy_btn_clicked.connect(self.jog_xy_clicked)
        self.jog_xy.joy_btn_released.connect(self.jog_xy_released)
        # program controls
        self.w.layout_program_control.addWidget(self.pgm_control)
        self.pgm_control.set_tooltip('T', "RUN")
        self.pgm_control.set_tooltip('L', "RELOAD")
        self.pgm_control.set_tooltip('R', "STEP")
        self.pgm_control.set_tooltip('B', "PAUSE")
        self.pgm_control.set_tooltip('C', "STOP")
        self.pgm_control.set_icon('L', 'image', 'qtdragon/images/reload.png')
        self.pgm_control.set_icon('R', 'image', 'qtdragon/images/step.png')
        self.pgm_control.set_icon('T', 'image', 'qtdragon/images/run.png')
        self.pgm_control.set_icon('B', 'image', 'qtdragon/images/pause.png')
        self.pgm_control.set_icon('C', 'image', 'qtdragon/images/stop.png')
        self.pgm_control.set_highlight_color(self.stop_color)
        self.pgm_control.set_highlight('C', True)
        self.pgm_control.joy_btn_clicked.connect(self.pgm_control_clicked)

    def processed_key_event__(self,receiver,event,is_pressed,key,code,shift,cntrl):
        # when typing in MDI, we don't want keybinding to call functions
        # so we catch and process the events directly.
        # We do want ESC, F1 and F2 to call keybinding functions though
        if code not in(QtCore.Qt.Key_Escape,QtCore.Qt.Key_F1 ,QtCore.Qt.Key_F2):
#                    QtCore.Qt.Key_F3,QtCore.Qt.Key_F4,QtCore.Qt.Key_F5):

            # search for the top widget of whatever widget received the event
            # then check if it's one we want the keypress events to go to
            flag = False
            receiver2 = receiver
            while receiver2 is not None and not flag:
                if isinstance(receiver2, QtWidgets.QDialog):
                    flag = True
                    break
                if isinstance(receiver2, QtWidgets.QLineEdit):
                    flag = True
                    break
                if isinstance(receiver2, MDI_WIDGET):
                    flag = True
                    break
                if isinstance(receiver2, GCODE):
                    flag = True
                    break
                if isinstance(receiver2, TOOL_TABLE):
                    flag = True
                    break
                if isinstance(receiver2, OFFSET_VIEW):
                    flag = True
                    break
                receiver2 = receiver2.parent()

            if flag:
                if isinstance(receiver2, GCODE):
                    # if in manual do our keybindings - otherwise
                    # send events to gcode widget
                    if STATUS.is_man_mode() == False:
                        if is_pressed:
                            receiver.keyPressEvent(event)
                            event.accept()
                        return True
                if is_pressed:
                    receiver.keyPressEvent(event)
                    event.accept()
                    return True
                else:
                    event.accept()
                    return True

        # ok if we got here then try keybindings
        try:
            KEYBIND.call(self,event,is_pressed,shift,cntrl)
            event.accept()
            return True
        except NameError as e:
            if is_pressed:
                LOG.debug('Exception in KEYBINDING: {}'.format (e))
                self.add_status('Exception in KEYBINDING: {}'.format (e))
        except Exception as e:
            if is_pressed:
                LOG.debug('Exception in KEYBINDING:', exc_info=e)
                print ('Error in, or no function for: %s in handler file for-%s'%(KEYBIND.convert(event),key))
        event.accept()
        return True

    #########################
    # CALLBACKS FROM STATUS #
    #########################

    def spindle_pwr_changed(self, data):
        # this calculation assumes the voltage is line to neutral
        # that the current reported by the VFD is total current for all 3 phases
        # and that the synchronous motor spindle has a power factor of 0.9
        power = float(self.spindle_volts.get() * self.spindle_amps.get() * 0.9) # V x I x PF
        pc_power = (power / float(self.max_spindle_power)) * 100
        if pc_power > 100:
            pc_power = 100
        self.w.spindle_power.setValue(int(pc_power))

    def dialog_return(self, w, message):
        rtn = message.get('RETURN')
        name = message.get('NAME')
        unhome_code = bool(message.get('ID') == '_unhome_')
        pause_code = bool(message.get('ID') == '_wait_resume_')
        clr_mdi_code = bool(message.get('ID') == '_clear_mdi_')
        if unhome_code and name == 'MESSAGE' and rtn is True:
            ACTION.SET_MACHINE_UNHOMED(-1)
        elif pause_code and name == 'MESSAGE':
            self.eoffset_clear.set(True)
            self.eoffset_count.set(0)
            self.spindle_inhibit.set(False)
            self.eoffset_clear.set(False)
        elif clr_mdi_code and name == 'MESSAGE' and rtn is True:
            self.w.mdihistory.model.clear()

    def command_stopped(self, obj):
        if self.w.chk_pause_spindle.isChecked():
            self.eoffset_clear.set(True)
            self.eoffset_count.set(0)
            self.spindle_inhibit.set(False)
            self.eoffset_clear.set(False)

    def user_system_changed(self, data):
        sys = self.system_list[int(data) - 1]
        self.w.actionbutton_rel.setText(sys)
        txt = sys.replace('.', '_')
        self.w["action_" + txt.lower()].setChecked(True)

    def metric_mode_changed(self, mode):
        unit = "MM" if mode else "IN"
        for i in self.unit_label_list:
            self.w['lbl_' + i].setText(unit)
        for i in self.unit_speed_list:
            self.w['lbl_' + i].setText(unit + "/MIN")
        unit = "M/MIN" if mode else "F/MIN"
        self.w.lbl_scs_units.setText(unit)
        if mode == INFO.MACHINE_IS_METRIC:
            self.factor = 1.0
        elif mode:
            self.factor = 25.4
        else:
            self.factor = 1/25.4
        maxv = self.w.adj_maxv_ovr.value * self.factor
        rapid = (self.w.adj_rapid_ovr.value / 100) * self.max_linear_velocity * self.factor
        self.w.lbl_max_rapid.setText("{:4.0f}".format(rapid))
        self.w.lbl_maxv.setText("{:4.0f}".format(maxv))

    def file_loaded(self, filename):
        if filename is not None:
            self.add_status("Loaded file {}".format(filename))
            self.w.progressBar.reset()
            self.last_loaded_program = filename
            self.w.lbl_runtime.setText("00:00:00")
        else:
            self.add_status("Filename not valid")

    def percent_loaded_changed(self, pc):
        if pc == self.progress: return
        self.progress = pc
        if pc < 0:
            self.w.progressBar.setValue(0)
            self.w.progressBar.setFormat('PROGRESS')
        else:
            self.w.progressBar.setValue(pc)
            self.w.progressBar.setFormat('LOADING: {}%'.format(pc))

    def percent_done_changed(self, pc):
        if pc == self.progress: return
        self.progress = pc
        if pc < 0:
            self.w.progressBar.setValue(0)
            self.w.progressBar.setFormat('PROGRESS')
        else:
            self.w.progressBar.setValue(pc)
            self.w.progressBar.setFormat('COMPLETE: {}%'.format(pc))

    def homed(self, obj, joint):
        i = int(joint)
        axis = INFO.GET_NAME_FROM_JOINT.get(i).lower()
        try:
            widget = self.w["dro_axis_{}".format(axis)]
            widget.setProperty('homed', True)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        except:
            pass

    def all_homed(self, obj):
        self.home_all = True
        self.w.btn_home_all.setText("ALL\nHOMED")
        self.w.btn_home_all.setProperty('homed', True)
        self.w.btn_home_all.style().unpolish(self.w.btn_home_all)
        self.w.btn_home_all.style().polish(self.w.btn_home_all)
        if self.first_turnon is True:
            self.first_turnon = False
            if self.w.chk_reload_tool.isChecked():
                command = "M61 Q{}".format(self.reload_tool)
                ACTION.CALL_MDI(command)
            if self.last_loaded_program is not None and self.w.chk_reload_program.isChecked():
                if os.path.isfile(self.last_loaded_program):
                    self.w.cmb_gcode_history.addItem(self.last_loaded_program)
                    self.w.cmb_gcode_history.setCurrentIndex(self.w.cmb_gcode_history.count() - 1)
                    ACTION.OPEN_PROGRAM(self.last_loaded_program)
        ACTION.SET_MANUAL_MODE()
        self.w.manual_mode_button.setChecked(True)

    def not_all_homed(self, obj, list):
        self.home_all = False
        self.w.btn_home_all.setText("HOME\nALL")
        self.w.btn_home_all.setProperty('homed', False)
        self.w.btn_home_all.style().unpolish(self.w.btn_home_all)
        self.w.btn_home_all.style().polish(self.w.btn_home_all)
        for i in INFO.AVAILABLE_JOINTS:
            if str(i) in list:
                axis = INFO.GET_NAME_FROM_JOINT.get(i).lower()
                try:
                    widget = self.w["dro_axis_{}".format(axis)]
                    widget.setProperty('homed', False)
                    widget.style().unpolish(widget)
                    widget.style().polish(widget)
                except:
                    pass

    def update_status(self):
        # runtimer
        if self.timer_on is False or STATUS.is_auto_paused(): return
        self.time_tenths += 1
        if self.time_tenths == 10:
            self.time_tenths = 0
            self.run_time += 1
            hours, remainder = divmod(self.run_time, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.w.lbl_runtime.setText("{:02d}:{:02d}:{:02d}".format(hours, minutes, seconds))

    def hard_limit_tripped(self, obj, tripped, list_of_tripped):
        self.add_status("Hard limits tripped")
        self.w.chk_override_limits.setEnabled(tripped)
        if not tripped:
            self.w.chk_override_limits.setChecked(False)
    
    #######################
    # CALLBACKS FROM FORM #
    #######################

    # main button bar
    def main_tab_changed(self, btn):
        index = btn.property("index")
        if index is None: return
        if STATUS.is_auto_mode() and index != TAB_SETTINGS:
            self.add_status("Cannot switch pages while in AUTO mode")
            self.w.main_tab_widget.setCurrentIndex(TAB_MAIN)
            self.w.btn_main.setChecked(True)
            return
        if index == TAB_FILE and self.w.btn_gcode_edit.isChecked():
            self.w.btn_gcode_edit.setChecked(False)
            self.w.btn_gcode_edit_clicked(False)
        self.w.main_tab_widget.setCurrentIndex(index)

    def mpg_scale_changed(self, btn):
        if self.w.chk_use_mpg.isChecked():
            self.scale_select_0.set(btn.property('sel0'))
            self.scale_select_1.set(btn.property('sel1'))

    # gcode frame
    def cmb_gcode_history_clicked(self):
        if self.w.cmb_gcode_history.currentIndex() == 0: return
        filename = self.w.cmb_gcode_history.currentText()
        if filename == self.last_loaded_program:
            self.add_status("Selected program is already loaded")
        else:
            ACTION.OPEN_PROGRAM(filename)

    # program frame
    def pgm_control_clicked(self, btn):
        if btn == 'T':
            self.btn_run_clicked()
        elif btn == 'B':
            if STATUS.is_on_and_idle(): return
            if STATUS.is_auto_paused():
                self.pgm_control.set_tooltip('B', "PAUSE")
                self.pgm_control.set_highlight_color(self.run_color)
                ACTION.PAUSE()
            else:
                self.pgm_control.set_tooltip('B', "RESUME")
                self.pgm_control.set_highlight_color(self.pause_color)
                ACTION.PAUSE()
                if self.w.chk_pause_spindle.isChecked():
                    self.pause_spindle()
        elif btn == "L":
            self.btn_reload_file_clicked()
        elif btn == "R":
            ACTION.STEP()
        elif btn == "C":
            ACTION.ABORT()
            self.pgm_control.set_tooltip('B', "PAUSE")
            self.pgm_control.set_highlight_color(self.stop_color)

    def btn_run_clicked(self):
        if self.w.main_tab_widget.currentIndex() != 0:
            return
        if not STATUS.is_auto_mode():
            self.add_status("Must be in AUTO mode to run a program")
            return
        if STATUS.is_auto_running():
            self.add_status("Program is already running")
            return
        self.pgm_control.set_highlight_color(self.run_color)
        self.run_time = 0
        self.w.lbl_runtime.setText("00:00:00")
        if self.start_line <= 1:
            ACTION.RUN(0)
        else:
            # instantiate run from line preset dialog
            info = '<b>Running From Line: {} <\b>'.format(self.start_line)
            mess = {'NAME':'RUNFROMLINE', 'TITLE':'Preset Dialog', 'ID':'_RUNFROMLINE', 'MESSAGE':info, 'LINE':self.start_line}
            ACTION.CALL_DIALOG(mess)
        self.add_status("Started program from line {}".format(self.start_line))
        self.timer_on = True

    def pause_spindle(self):
        # set external offsets to lift spindle
        fval = float(self.w.lineEdit_eoffset_count.text())
        self.eoffset_count.set(int(fval))
        self.spindle_inhibit.set(True)
        self.add_status("Spindle paused")
        # instantiate warning box
        info = "Wait for spindle at speed signal before resuming"
        mess = {'NAME':'MESSAGE', 'ICON':'WARNING', 'ID':'_wait_resume_', 'MESSAGE':'CAUTION', 'MORE':info, 'TYPE':'OK'}
        ACTION.CALL_DIALOG(mess)

    def btn_reload_file_clicked(self):
        if self.last_loaded_program:
            self.w.progressBar.reset()
            self.add_status("Loaded program file {}".format(self.last_loaded_program))
            ACTION.OPEN_PROGRAM(self.last_loaded_program)

    def chk_run_from_line_changed(self, state):
        self.w.gcodegraphics.set_inhibit_selection(not state)
        text = "ENABLED" if state else "DISABLED"
        self.w.lbl_start_line.setText(text)
        if not state:
            self.start_line = 1

    def chk_pause_spindle_changed(self, state):
        text = 'ENABLED' if state else 'DISABLED'
        self.w.lbl_spindle_pause.setText(text)

    # jogging frame
    def jog_xy_clicked(self, btn):
        if btn not in ("L", "R", "T", "B"): return
        axis = 0 if btn == "L" or btn == "R" else 1
        direction = 1 if btn == "T" or btn == "R" else -1
        ACTION.ensure_mode(linuxcnc.MODE_MANUAL)
        ACTION.DO_JOG(axis, direction)

    def jog_xy_released(self, btn):
        if btn not in ("L", "R", "T", "B"): return
        if STATUS.get_jog_increment() != 0: return
        axis = 0 if btn == "L" or btn == "R" else 1
        ACTION.ensure_mode(linuxcnc.MODE_MANUAL)
        ACTION.DO_JOG(axis, 0)

    def jog_az_clicked(self, btn):
        if btn not in ("L", "R", "T", "B"): return
        axis = 3 if btn == "L" or btn == "R" else 2
        direction = 1 if btn == "T" or btn == "R" else -1
        ACTION.ensure_mode(linuxcnc.MODE_MANUAL)
        ACTION.DO_JOG(axis, direction)

    def jog_az_released(self, btn):
        if btn not in ("L", "R", "T", "B"): return
        if STATUS.get_jog_increment() != 0: return
        axis = 3 if btn == "L" or btn == "R" else 2
        ACTION.ensure_mode(linuxcnc.MODE_MANUAL)
        ACTION.DO_JOG(axis, 0)

    def chk_use_mpg_changed(self, state):
        if not state:
            self.scale_select_0.set(1)
            self.scale_select_1.set(1)
            if "X" in self.axis_list: self.jog_xy.set_highlight('X', True)
            if "Y" in self.axis_list: self.jog_xy.set_highlight('Y', True)
            if "Z" in self.axis_list: self.jog_az.set_highlight('Z', True)
            if "A" in self.axis_list: self.jog_az.set_highlight('A', True)
        else:
            self.show_selected_axis(None)
            if   self.w.btn_scale_1.isChecked():
                self.scale_select_0.set(self.w.btn_scale_1.property('sel0'))
                self.scale_select_1.set(self.w.btn_scale_1.property('sel1'))
            elif self.w.btn_scale_10.isChecked():
                self.scale_select_0.set(self.w.btn_scale_10.property('sel0'))
                self.scale_select_1.set(self.w.btn_scale_10.property('sel1'))
            elif self.w.btn_scale_100.isChecked():
                self.scale_select_0.set(self.w.btn_scale_100.property('sel0'))
                self.scale_select_1.set(self.w.btn_scale_100.property('sel1'))

    # offsets frame
    def btn_goto_location_clicked(self):
        dest = self.w.sender().property('location')
        factor = 1 if STATUS.is_metric_mode() else 1/25.4
        ACTION.CALL_MDI("G90")
        if dest == 'home':
            x = float(self.w.lbl_home_x.text()) * factor
            y = float(self.w.lbl_home_y.text()) * factor
            ACTION.CALL_MDI_WAIT("G53 G0 Z0")
            command = "G53 G0 X{:3.4f} Y{:3.4f}".format(x, y)
        elif dest == 'sensor':
            x = float(self.w.lineEdit_sensor_x.text()) * factor
            y = float(self.w.lineEdit_sensor_y.text()) * factor
            ACTION.CALL_MDI_WAIT("G53 G0 Z0")
            command = "G53 G0 X{:3.4f} Y{:3.4f}".format(x, y)
        elif dest == 'zero':
            ACTION.CALL_MDI_WAIT("G53 G0 Z0")
            command = "G0 X0 Y0"
        elif dest == 'zero_a':
            command = "G0 A0"
        ACTION.CALL_MDI_WAIT(command,10)

    def btn_ref_laser_clicked(self):
        if self.w.btn_laser_on.isChecked():
            x = float(self.w.lineEdit_laser_x.text())
            y = float(self.w.lineEdit_laser_y.text())
            if not STATUS.is_metric_mode():
                x = x / 25.4
                y = y / 25.4
            self.add_status("Laser offsets set")
            command = "G10 L20 P0 X{:3.4f} Y{:3.4f}".format(x, y)
            ACTION.CALL_MDI(command)
        else:
            self.add_status("Laser must be on to set laser offset")

    def btn_touchoff_clicked(self):
        if STATUS.get_current_tool() == 0:
            self.add_status("Cannot touchoff with no tool loaded")
            return
        if not STATUS.is_all_homed():
            self.add_status("Must be homed to perform tool touchoff")
            return
        sensor = self.w.sender().property('sensor')
        self.touchoff(sensor)

    # DRO frame
    def btn_home_all_clicked(self, obj):
        if self.home_all is False:
            ACTION.SET_MACHINE_HOMING(-1)
        else:
        # instantiate dialog box
            info = "Unhome All Axes?"
            mess = {'NAME':'MESSAGE', 'ID':'_unhome_', 'MESSAGE':'UNHOME ALL', 'MORE':info, 'TYPE':'OKCANCEL'}
            ACTION.CALL_DIALOG(mess)

    def btn_zero_a_clicked(self):
        ACTION.SET_AXIS_ORIGIN('A', 0)

    # override frame
    def slow_button_clicked(self, state):
        adj = self.w.sender().property('adj')
        if state:
            self.w.sender().setText("SLOW")
            value = int(self.w[adj].value / self.slow_jog_factor)
            maxval = int(self.w[adj].maximum() / self.slow_jog_factor)
            hival = int(self.w[adj].hi_value / self.slow_jog_factor)
            lowval = int(self.w[adj].low_value / self.slow_jog_factor)
            step = 10
        else:
            self.w.sender().setText("FAST")
            value = int(self.w[adj].value * self.slow_jog_factor)
            maxval = int(self.w[adj].maximum() * self.slow_jog_factor)
            hival = int(self.w[adj].hi_value * self.slow_jog_factor)
            lowval = int(self.w[adj].low_value * self.slow_jog_factor)
            step = 100
        self.w[adj].low_value = lowval
        self.w[adj].hi_value = hival
        self.w[adj].setMaximum(maxval)
        self.w[adj].setValue(value)
        self.w[adj].setStep(step)
        self.w[adj].valueChanged.emit(value)

    def adj_rapid_changed(self, value):
        rapid = (value / 100) * self.max_linear_velocity * self.factor
        self.w.lbl_max_rapid.setText("{:4.0f}".format(rapid))

    def adj_maxv_changed(self, value):
        self.w.lbl_maxv.setText("{:4.0f}".format(value * self.factor))

    def adj_feed_ovr_changed(self, value):
        frac = int(value * self.max_linear_velocity / 100)
        self.w.gauge_feedrate.set_threshold(frac)

    def adj_spindle_ovr_changed(self, value):
        frac = int(value * self.max_spindle_rpm / 100)
        self.w.gauge_spindle.set_threshold(frac)

    # file tab
    def btn_gcode_edit_clicked(self, state):
        if not STATUS.is_on_and_idle():
            return
        if state:
            self.w.filemanager.hide()
            self.w.gcode_editor.show()
            self.w.gcode_editor.editMode()
        else:
            self.w.filemanager.show()
            self.w.gcode_editor.hide()
            self.w.gcode_editor.readOnlyMode()

    def btn_load_file_clicked(self):
        if self.w.btn_gcode_edit.isChecked(): return
        fname = self.w.filemanager.getCurrentSelected()
        if fname[1] is True:
            self.load_code(fname[0])

    def btn_copy_file_clicked(self):
        if self.w.btn_gcode_edit.isChecked(): return
        if self.w.sender() == self.w.btn_copy_right:
            source = self.w.filemanager_usb.getCurrentSelected()
            target = self.w.filemanager.getCurrentSelected()
        elif self.w.sender() == self.w.btn_copy_left:
            source = self.w.filemanager.getCurrentSelected()
            target = self.w.filemanager_usb.getCurrentSelected()
        else:
            return
        if source[1] is False:
            self.add_status("Specified source is not a file")
            return
        if target[1] is True:
            destination = os.path.join(os.path.dirname(target[0]), os.path.basename(source[0]))
        else:
            destination = os.path.join(target[0], os.path.basename(source[0]))
        try:
            copyfile(source[0], destination)
            self.add_status("Copied file from {} to {}".format(source[0], destination))
        except Exception as e:
            self.add_status("Unable to copy file. %s" %e)

    # tool tab
    def btn_load_tool_clicked(self):
        checked = self.w.tooloffsetview.get_checked_list()
        if len(checked) > 1:
            self.add_status("Select only 1 tool to load")
        elif checked:
            self.add_status("Loaded tool {}".format(checked[0]))
            ACTION.CALL_MDI("M61 Q{} G43".format(checked[0]))
        else:
            self.add_status("No tool selected")

    # status tab
    def btn_clear_status_clicked(self):
        STATUS.emit('update-machine-log', None, 'DELETE')

    def btn_save_log_clicked(self):
        if self.w.btn_select_log.isChecked():
            text = self.w.integrator_log.toPlainText()
        else:
            text = self.w.machinelog.toPlainText()
        filename = self.w.lbl_clock.text()
        filename = 'status_' + filename.replace(' ','_') + '.txt'
        self.add_status("Saving log to {}".format(filename))
        with open(filename, 'w') as f:
            f.write(text)

    def btn_dimensions_clicked(self, state):
        self.w.gcodegraphics.show_extents_option = state
        self.w.gcodegraphics.clear_live_plotter()
        
    # camview tab
    def cam_zoom_changed(self, value):
        self.w.camview.scale = float(value) / 10

    def cam_dia_changed(self, value):
        self.w.camview.diameter = value

    def cam_rot_changed(self, value):
        self.w.camview.rotation = float(value) / 10

    def btn_ref_camera_clicked(self):
        x = float(self.w.lineEdit_camera_x.text())
        y = float(self.w.lineEdit_camera_y.text())
        if not STATUS.is_metric_mode():
            x = x / 25.4
            y = y / 25.4
        self.add_status("Camera offsets set")
        command = "G10 L20 P0 X{:3.4f} Y{:3.4f}".format(x, y)
        ACTION.CALL_MDI(command)

    # settings tab
    def chk_override_limits_changed(self, state):
        if state:
            print("Override limits set")
            ACTION.SET_LIMITS_OVERRIDE()
        else:
            print("Override limits not set")

    def alpha_mode_clicked(self, state):
        self.w.gcodegraphics.set_alpha_mode(state)

    def chk_use_camera_changed(self, state):
        if state :
            self.w.btn_camera.show()
        else:
            self.w.btn_camera.hide()

    def chk_use_tool_sensor_changed(self, state):
        self.w.btn_tool_sensor.setEnabled(state)
        self.w.btn_goto_sensor.setEnabled(state)
        self.w.widget_toolsensor_height.setEnabled(state)
        self.w.widget_workpiece_height.setEnabled(state)

    def chk_use_touchplate_changed(self, state):
        self.w.btn_touchplate.setEnabled(state)
        self.w.widget_touchplate_height.setEnabled(state)

    def apply_stylesheet_clicked(self):
        if self.w.cmb_stylesheet.currentText() == "As Loaded": return
        self.styleeditor.styleSheetCombo.setCurrentIndex(self.w.cmb_stylesheet.currentIndex())
        self.styleeditor.on_applyButton_clicked()

    def btn_clear_mdi_clicked(self):
        info = "This will clear the MDI history window, not the mdi history file"
        mess = {'NAME':'MESSAGE', 'ICON':'WARNING', 'ID':'_clear_mdi_', 'MESSAGE':'CAUTION', 'MORE':info, 'TYPE':'OKCANCEL'}
        ACTION.CALL_DIALOG(mess)
        
    #####################
    # GENERAL FUNCTIONS #
    #####################
    def show_selected_axis(self, obj):
        if self.w.chk_use_mpg.isChecked():
            self.jog_xy.set_highlight('X', bool(self.axis_select_x.get() is True))
            self.jog_xy.set_highlight('Y', bool(self.axis_select_y.get() is True))
            self.jog_az.set_highlight('Z', bool(self.axis_select_z.get() is True))
            if 'A' in self.axis_list:
                self.jog_az.set_highlight('A', bool(self.axis_select_a.get() is True))

    def load_code(self, fname):
        if fname is None: return
        if fname.endswith(".ngc") or fname.endswith(".py"):
            self.w.cmb_gcode_history.addItem(fname)
            self.w.cmb_gcode_history.setCurrentIndex(self.w.cmb_gcode_history.count() - 1)
            ACTION.OPEN_PROGRAM(fname)
            self.add_status("Loaded program file : {}".format(fname))
            self.w.main_tab_widget.setCurrentIndex(TAB_MAIN)
        elif fname.endswith(".html"):
            try:
                url = QtCore.QUrl("file:///" + fname)
                self.web_view.load(url)
                self.add_status("Loaded HTML file : {}".format(fname))
                self.w.main_tab_widget.setCurrentIndex(TAB_SETUP)
                self.w.btn_setup.setChecked(True)
            except Exception as e:
                print("Error loading HTML file : {}".format(e))
        else:
            self.add_status("Unknown or invalid filename")

    def disable_spindle_pause(self):
        self.eoffset_count.set(0)
        self.spindle_inhibit.set(False)

    def touchoff(self, selector):
        if selector == 'touchplate':
            z_offset = self.w.lineEdit_touch_height.text()
        elif selector == 'toolsensor':
            z_offset = float(self.w.lineEdit_sensor_height.text()) - float(self.w.lineEdit_work_height.text())
            z_offset = str(z_offset)
        else:
            self.add_status("Unknown touchoff routine specified")
            return
        self.add_status("Touchoff to {} started".format(selector))
        max_probe = self.w.lineEdit_max_probe.text()
        search_vel = self.w.lineEdit_search_vel.text()
        probe_vel = self.w.lineEdit_probe_vel.text()
        self.start_touchoff()
        string_to_send = "probe_down$" + search_vel + "$" + probe_vel + "$" + max_probe + "$" + z_offset + "\n"
        self.proc.writeData(bytes(string_to_send, 'utf-8'))

    def kb_jog(self, state, joint, direction, fast = False, linear = True):
        if not STATUS.is_man_mode() or not STATUS.machine_is_on():
            self.add_status('Machine must be ON and in Manual mode to jog')
            return
        if linear:
            distance = STATUS.get_jog_increment()
            rate = STATUS.get_jograte()/60
        else:
            distance = STATUS.get_jog_increment_angular()
            rate = STATUS.get_jograte_angular()/60
        if state:
            if fast:
                rate = rate * 2
            ACTION.JOG(joint, direction, rate, distance)
        else:
            ACTION.JOG(joint, 0, 0, 0)

    def add_status(self, message):
        self.w.statusbar.showMessage(message)
        STATUS.emit('update-machine-log', message, 'TIME')

    def enable_auto(self, state):
        if state:
            self.w.btn_main.setChecked(True)
            self.w.main_tab_widget.setCurrentIndex(TAB_MAIN)

    def enable_onoff(self, state):
        text = "ON" if state else "OFF"
        self.add_status("Machine " + text)
        self.eoffset_count.set(0)
        for widget in self.onoff_list:
            self.w["frame_" + widget].setEnabled(state)
        self.jog_xy.setEnabled(state)
        self.jog_az.setEnabled(state)
        self.pgm_control.setEnabled(state)

    def set_start_line(self, line):
        self.w.gcodegraphics.highlight_graphics(line)
        if self.w.chk_run_from_line.isChecked():
            self.start_line = line
            self.w.lbl_start_line.setText("{}".format(self.start_line))

    def use_keyboard(self):
        if self.w.chk_use_keyboard.isChecked():
            return True
        else:
            self.add_status('Keyboard shortcuts are disabled')
            return False

    def stop_timer(self):
        self.pgm_control.set_highlight_color(self.stop_color)
        if self.timer_on:
            self.timer_on = False
            self.add_status("Run timer stopped at {}".format(self.w.lbl_runtime.text()))

    def start_touchoff(self):
        if self.proc is not None:
            self.add_status("Touchoff routine is already running")
            return
        self.proc = QtCore.QProcess()
        self.proc.setReadChannel(QtCore.QProcess.StandardOutput)
        self.proc.started.connect(self.touchoff_started)
        self.proc.readyReadStandardOutput.connect(self.read_stdout)
        self.proc.readyReadStandardError.connect(self.read_stderror)
        self.proc.finished.connect(self.touchoff_finished)
        self.proc.start('python3 {}'.format(SUBPROGRAM))

    def read_stdout(self):
        qba = self.proc.readAllStandardOutput()
        line = qba.data()
        self.parse_line(line)

    def read_stderror(self):
        qba = self.proc.readAllStandardError()
        line = qba.data()
        self.parse_line(line)

    def parse_line(self, line):
        line = line.decode("utf-8")
        if "COMPLETE" in line:
            self.add_status("Touchoff routine returned success")
        elif "ERROR" in line:
            self.add_status(line)

    def touchoff_started(self):
        LOG.info("TouchOff subprogram started with PID {}\n".format(self.proc.processId()))

    def touchoff_finished(self, exitCode, exitStatus):
        LOG.info("Touchoff Process finished - exitCode {} exitStatus {}".format(exitCode, exitStatus))
        self.proc = None

    #####################
    # KEY BINDING CALLS #
    #####################

    def on_keycall_ESTOP(self,event,state,shift,cntrl):
        if state:
            ACTION.SET_ESTOP_STATE(True)

    def on_keycall_POWER(self,event,state,shift,cntrl):
        if state:
            ACTION.SET_MACHINE_STATE(False)

    def on_keycall_ABORT(self,event,state,shift,cntrl):
        if state:
            ACTION.ABORT()

    def on_keycall_HOME(self,event,state,shift,cntrl):
        if state and not STATUS.is_all_homed() and self.use_keyboard():
            ACTION.SET_MACHINE_HOMING(-1)

    def on_keycall_PAUSE(self,event,state,shift,cntrl):
        if state and STATUS.is_auto_mode() and self.use_keyboard():
            ACTION.PAUSE()

    def on_keycall_XPOS(self,event,state,shift,cntrl):
        if self.use_keyboard():
            self.kb_jog(state, 0, 1, shift)

    def on_keycall_XNEG(self,event,state,shift,cntrl):
        if self.use_keyboard():
            self.kb_jog(state, 0, -1, shift)

    def on_keycall_YPOS(self,event,state,shift,cntrl):
        if self.use_keyboard():
            self.kb_jog(state, 1, 1, shift)

    def on_keycall_YNEG(self,event,state,shift,cntrl):
        if self.use_keyboard():
            self.kb_jog(state, 1, -1, shift)

    def on_keycall_ZPOS(self,event,state,shift,cntrl):
        if self.use_keyboard():
            self.kb_jog(state, 2, 1, shift)

    def on_keycall_ZNEG(self,event,state,shift,cntrl):
        if self.use_keyboard():
            self.kb_jog(state, 2, -1, shift)
    
    def on_keycall_APOS(self,event,state,shift,cntrl):
        if self.use_keyboard():
            self.kb_jog(state, 3, 1, shift, False)

    def on_keycall_ANEG(self,event,state,shift,cntrl):
        if self.use_keyboard():
            self.kb_jog(state, 3, -1, shift, False)

    def on_keycall_F4(self,event,state,shift,cntrl):
        if state:
            mess = {'NAME':'CALCULATOR', 'TITLE':'Calculator', 'ID':'_calculator_'}
            ACTION.CALL_DIALOG(mess)

    def on_keycall_F12(self,event,state,shift,cntrl):
        if state:
            self.styleeditor.load_dialog()

    ##############################
    # required class boiler code #
    ##############################
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)

################################
# required handler boiler code #
################################

def get_handlers(halcomp, widgets, paths):
    return [HandlerClass(halcomp, widgets, paths)]

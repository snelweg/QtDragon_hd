#!/usr/bin/python

class Connections():
    def __init__(self, parent, widget):
        self.w = widget
        self.parent = parent
        # buttons
        self.w.btn_run.clicked.connect(self.parent.btn_run_clicked)
        self.w.btn_pause_spindle.clicked.connect(lambda state: self.parent.btn_pause_spindle_clicked(state))
        self.w.btn_jog_l_slow.clicked.connect(self.parent.slow_button_clicked)
        self.w.btn_jog_a_slow.clicked.connect(self.parent.slow_button_clicked)
        self.w.btn_load_file.clicked.connect(self.parent.btn_load_file_clicked)
        self.w.btn_reload_file.clicked.connect(self.parent.btn_reload_file_clicked)
        self.w.btn_gcode_edit.clicked.connect(self.parent.btn_gcode_edit_clicked)
        self.w.btn_copy_right.clicked.connect(self.parent.btn_copy_file_clicked)
        self.w.btn_copy_left.clicked.connect(self.parent.btn_copy_file_clicked)
        self.w.btn_save_status.clicked.connect(self.parent.btn_save_status_clicked)
        self.w.btn_clear_status.clicked.connect(self.parent.btn_clear_status_clicked)
        self.w.btn_home_all.clicked.connect(self.parent.btn_home_all_clicked)
        self.w.btn_ref_laser.clicked.connect(self.parent.btn_ref_laser_clicked)
        self.w.btn_ref_camera.clicked.connect(self.parent.btn_ref_camera_clicked)
        self.w.btn_goto_zero.clicked.connect(self.parent.btn_goto_location_clicked)
        self.w.btn_goto_sensor.clicked.connect(self.parent.btn_goto_location_clicked)
        self.w.btn_go_home.clicked.connect(self.parent.btn_goto_location_clicked)
        self.w.btn_load_tool.clicked.connect(self.parent.btn_load_tool_clicked)
        self.w.btn_tool_sensor.clicked.connect(self.parent.btn_touchoff_clicked)
        self.w.btn_touchplate.clicked.connect(self.parent.btn_touchoff_clicked)
        self.w.btn_maxv_ovr_50.clicked.connect(self.parent.btn_maxv_50_clicked)
        self.w.btn_maxv_ovr_100.clicked.connect(self.parent.btn_maxv_100_clicked)
        self.w.btn_dimensions.clicked.connect(lambda state: self.parent.btn_dimensions_clicked(state))
        # action buttons
        # checkboxes
        self.w.chk_use_mpg.stateChanged.connect(lambda state: self.parent.chk_use_mpg_changed(state))
        self.w.chk_override_limits.stateChanged.connect(lambda state: self.parent.chk_override_limits_changed(state))
        self.w.chk_use_tool_sensor.stateChanged.connect(lambda state: self.parent.chk_use_tool_sensor_changed(state))
        self.w.chk_use_touchplate.stateChanged.connect(lambda state: self.parent.chk_use_touchplate_changed(state))
        self.w.chk_use_virtual.stateChanged.connect(lambda state: self.parent.chk_use_virtual_changed(state))
        self.w.chk_use_camera.stateChanged.connect(lambda state: self.parent.chk_use_camera_changed(state))
        self.w.chk_run_from_line.stateChanged.connect(lambda state: self.parent.chk_run_from_line_changed(state))
        self.w.chk_lock_tsh.stateChanged.connect(lambda state: self.w.lineEdit_sensor_height.setReadOnly(not state))
        self.w.chk_lock_tph.stateChanged.connect(lambda state: self.w.lineEdit_touch_height.setReadOnly(not state))
        self.w.chk_lock_wph.stateChanged.connect(lambda state: self.w.lineEdit_work_height.setReadOnly(not state))
        # sliders
        self.w.slider_feed_ovr.valueChanged.connect(lambda value: self.parent.slider_feed_ovr_changed(value))
        self.w.slider_spindle_ovr.valueChanged.connect(lambda value: self.parent.slider_spindle_ovr_changed(value))
        self.w.slider_rapid_ovr.valueChanged.connect(lambda value: self.parent.slider_rapid_changed(value))
        self.w.slider_maxv_ovr.valueChanged.connect(lambda value: self.parent.slider_maxv_changed(value))
        self.w.cam_diameter.valueChanged.connect(lambda value: self.parent.cam_dia_changed(value))
        self.w.cam_rotate.valueChanged.connect(lambda value: self.parent.cam_rot_changed(value))
        # comboboxes
        self.w.cmb_gcode_history.activated.connect(self.parent.cmb_gcode_history_clicked)
        self.w.cmb_stylesheet.currentIndexChanged.connect(self.parent.apply_stylesheet_clicked)
        # misc
        self.w.gcode_viewer.percentDone.connect(lambda percent: self.parent.percent_done_changed(percent))
        self.w.gcodegraphics.percentLoaded.connect(lambda percent: self.parent.percent_loaded_changed(percent))

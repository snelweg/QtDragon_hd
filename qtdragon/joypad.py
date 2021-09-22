#!/usr/bin/python
# Qtvcp Joypad widget
#
# Copyright (c) 2021  Jim Sloot <persei802@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
###############################################################################
import sys
import hal
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QPoint, QPointF, QLineF, QRect, QRectF, QSize, QSizeF, QEvent
from PyQt5.QtGui import QPainter, QPainterPath, QPen, QBrush, QColor, QFont, QPixmap, QRadialGradient

class JoyPad(QtWidgets.QWidget):
    joy_btn_clicked = QtCore.pyqtSignal(str)
    joy_btn_released = QtCore.pyqtSignal(str)
    def __init__(self, parent=None):
        super(JoyPad, self).__init__(parent)
        self.rect1 = QRectF()
        self.rect2 = QRectF()
        self.left_image = None
        self.right_image = None
        self.top_image = None
        self.bottom_image = None
        self.center_image = None
        self.highlight_color = QColor('gray')
        self.highlight_left = False
        self.highlight_right = False
        self.highlight_top = False
        self.highlight_bottom = False
        self.highlight_center = False
        self.last_active_btn = None
        self.setMouseTracking(True)
        self.setToolTipDuration(2000)
        self.installEventFilter(self)
        self.btn_names = {'L': 'left', 'R': 'right', 'T': 'top', 'B': 'bottom', 'C': 'center'}
        self.tooltips = {'L': '', 'R': '', 'T': '', 'B': '', 'C': ''}
        self.axis_list = ('X', 'Y', 'Z', 'A')

    def eventFilter(self, obj, event):
        if obj is self and self.isEnabled():
            if event.type() == QEvent.MouseButtonPress:
                if event.button() == Qt.RightButton:
                    event.ignore()
                else:
                    pos = event.localPos()
                    active_btn = self.get_active_btn(pos)
                    self.last_active_btn = active_btn
                    if active_btn is not None:
                        self.joy_btn_clicked.emit(active_btn)
            elif event.type() == QEvent.MouseButtonRelease:
                if event.button() == Qt.RightButton:
                    event.ignore()
                elif self.last_active_btn is not None:
                    self.joy_btn_released.emit(self.last_active_btn)
            elif event.type() == QEvent.MouseMove:
                pos = event.pos()
                active_btn = self.get_active_btn(pos)
                if active_btn is not None:
                    self.setToolTip(self.tooltips[active_btn])
        return super(JoyPad, self).eventFilter(obj, event)

    def get_active_btn(self, pos):
        if self.center_path.contains(pos): return 'C'
        elif self.left_path.contains(pos): return 'L'
        elif self.right_path.contains(pos): return 'R'
        elif self.bottom_path.contains(pos): return 'B'
        elif self.top_path.contains(pos): return 'T'
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(painter.Antialiasing)
        w = min(event.rect().width(), event.rect().height())
        self.rect1.setSize(QSizeF(w * 0.4, w * 0.4))
        self.rect2.setSize(QSizeF(w * 0.9, w * 0.9))
        self.create_paths(painter, event)
        self.draw_painter_paths(painter, event)
        self.draw_icons(painter, event)
        self.draw_highlight(painter, event)
        painter.end()

    def create_paths(self, qp, event):
        self.left_path = QPainterPath()
        self.right_path = QPainterPath()
        self.bottom_path = QPainterPath()
        self.top_path = QPainterPath()
        self.center_path = QPainterPath()
        center = event.rect().center()
        self.rect1.moveCenter(center)
        self.rect2.moveCenter(center)
        left_start = QPointF(self.rect1.topLeft())
        right_start = QPointF(self.rect1.bottomRight())
        bottom_start = QPointF(self.rect1.bottomLeft())
        top_start = QPointF(self.rect1.topRight())
        path = (self.right_path, self.top_path, self.left_path, self.bottom_path)
        start = (right_start, top_start, left_start, bottom_start)
        angle = -45
        for i in range(4):
            path[i].moveTo(start[i])
            path[i].arcTo(self.rect1, angle, 90)
            path[i].arcTo(self.rect2, angle + 90, -90)
            path[i].closeSubpath()
            angle += 90
        cap = QRectF()
        cap.setSize(QSizeF(self.rect1.width()*0.8, self.rect1.height()*0.8))
        cap.moveCenter(center)
        self.center_path.addEllipse(cap)

    def draw_painter_paths(self, qp, event):
        w = min(event.rect().width(), event.rect().height())
        center = event.rect().center()
        fp = QPoint(center.x() - w/4, center.y() - w/4)
        bg = QRadialGradient(center, w/2, fp)
        bg.setColorAt(0, QColor(180, 180, 180))
        bg.setColorAt(1, QColor(40, 40, 40))
        qp.setBrush(QBrush(bg))
        qp.setPen(QPen(QColor(Qt.black), 4))
        qp.drawPath(self.left_path)
        qp.drawPath(self.right_path)
        qp.drawPath(self.top_path)
        qp.drawPath(self.bottom_path)
        qp.drawPath(self.center_path)

    def draw_icons(self, qp, event):
        rect = QRect()
        rect.setSize(QSize(self.rect1.width() * 0.4, self.rect1.height() * 0.4))
        center = event.rect().center()
        qp.setPen(QPen(Qt.white, 2))
        qp.setFont(QFont('Lato Heavy', 20))
        # left button
        rect.moveCenter(QPoint(center.x() - self.rect2.width()/3, center.y()))
        if isinstance(self.left_image, QPixmap):
            pix = self.left_image
            qp.drawPixmap(rect, pix, pix.rect())
        elif isinstance(self.left_image, str):
            qp.drawText(rect, Qt.AlignCenter, self.left_image)
        # right button
        rect.moveCenter(QPoint(center.x() + self.rect2.width()/3, center.y()))
        if isinstance(self.right_image, QPixmap):
            pix = self.right_image
            qp.drawPixmap(rect, pix, pix.rect())
        elif isinstance(self.right_image, str):
            qp.drawText(rect, Qt.AlignCenter, self.right_image)
        # bottom button
        rect.moveCenter(QPoint(center.x(), center.y() + self.rect2.width()/3))
        if isinstance(self.bottom_image, QPixmap):
            pix = self.bottom_image
            qp.drawPixmap(rect, pix, pix.rect())
        elif isinstance(self.bottom_image, str):
            qp.drawText(rect, Qt.AlignCenter, self.bottom_image)
        # top button
        rect.moveCenter(QPoint(center.x(), center.y() - self.rect2.width()/3))
        if isinstance(self.top_image, QPixmap):
            pix = self.top_image
            qp.drawPixmap(rect, pix, pix.rect())
        elif isinstance(self.top_image, str):
            qp.drawText(rect, Qt.AlignCenter, self.top_image)
        # center button
        rect.moveCenter(QPoint(center.x(), center.y()))
        if isinstance(self.center_image, QPixmap):
            pix = self.center_image
            qp.drawPixmap(rect, pix, pix.rect())
        elif isinstance(self.center_image, str):
            qp.drawText(rect, Qt.AlignCenter, self.center_image)

    def draw_highlight(self, qp, event):
        rect = QRectF()
        rect.setSize(self.rect1.size() * 0.9)
        center = event.rect().center()
        rect.moveCenter(center)
        pen_width = self.rect1.width() * 0.08
        qp.setPen(QPen(self.highlight_color, pen_width, cap = Qt.FlatCap))
        if self.highlight_right is True:
            qp.drawArc(rect, -45 * 16, 90 * 16)
        if self.highlight_left is True:
            qp.drawArc(rect, 135 * 16, 90 * 16)
        if self.highlight_top is True:
            qp.drawArc(rect, 45 * 16, 90 * 16)
        if self.highlight_bottom is True:
            qp.drawArc(rect, 225 * 16, 90 * 16)
        if self.highlight_center is True:
            qp.drawArc(rect, 0, 5760)

    def set_highlight(self, btn, state):
        if btn not in self.axis_list and btn not in self.btn_names.keys(): return
        if btn == 'X' or btn == 'A':
            self.highlight_left = state
            self.highlight_right = state
        elif btn == 'Y' or btn == 'Z':
            self.highlight_top = state
            self.highlight_bottom = state
        else:
            name = self.btn_names[btn]
            self['highlight_' + name] = state
        self.update()

    def set_icon(self, btn, kind, data):
        if btn not in self.btn_names.keys(): return
        name = self.btn_names[btn]
        if kind == 'image':
            self[name + "_image"] = QPixmap(data)
        elif kind == 'text':
            self[name + "_image"] = data
        else: return
        self.update()

    def set_tooltip(self, btn, tip):
        if btn in self.btn_names.keys():
            self.tooltips[btn] = tip

    @QtCore.pyqtSlot(QColor)
    def set_highlight_color(self, color):
        self.highlight_color = color
        self.update()

    def get_highlight_color(self):
        return self.highlight_color

    def reset_highlight_color(self):
        self.highlight_color = QColor('gray')

    HighlightColor = QtCore.pyqtProperty(QColor, get_highlight_color, set_highlight_color, reset_highlight_color)

    @QtCore.pyqtSlot(str)
    def btn_clicked(self, btn):
        print("Button clicked", btn)

    @QtCore.pyqtSlot(str)
    def btn_released(self, btn):
        print("Button released", btn)

    # required code for object indexing
    def __getitem__(self, item):
        return getattr(self, item)

    def __setitem__(self, item, value):
        return setattr(self, item, value)

    #############################
    # Testing                   #
    #############################
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QWidget, QVBoxLayout, QApplication
    app = QtWidgets.QApplication(sys.argv)
    w = QWidget()
    w.setGeometry(100, 100, 600, 400)
    w.setWindowTitle('JoyPad')
    joy = JoyPad()
    joy.set_icon('L', 'text', 'X-')
    joy.set_icon('R', 'text', 'X+')
    joy.set_icon('T', 'text', 'Y+')
    joy.set_icon('B', 'text', 'Y-')
    joy.set_icon('C', 'image', 'stop.png')
    joy.set_tooltip('T', 'This is the top button')
    joy.set_tooltip('C', 'This is the center button')
    joy.set_highlight_color('red')
    joy.set_highlight('C', True)
    joy.joy_btn_clicked.connect(joy.btn_clicked)
    joy.joy_btn_released.connect(joy.btn_released)
    layout = QtWidgets.QVBoxLayout()
    layout.addWidget(joy)
    w.setLayout(layout)
    w.show()
    sys.exit( app.exec_() )

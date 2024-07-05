import sys
import os
import json
import base64
from datetime import datetime
from time import time
from copy import deepcopy

from PyQt5.QtWidgets import (
  QApplication, 
  QWidget, 
  QVBoxLayout, 
  QPushButton, 
  QLabel, 
  QGridLayout,
  QFrame, 
  QMessageBox, 
  QTextEdit, 
  QDialog, 
  QHBoxLayout, 
  QSpacerItem, 
  QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap, QIcon
import pyqtgraph as pg

from pyqtgraph import AxisItem

from utils.const import *
from utils.docker import _DockerUtilsMixin

from utils.icon import ICON_BASE64

from ver import __VER__ as __version__

def get_icon_from_base64(base64_str):
  icon_data = base64.b64decode(base64_str)
  pixmap = QPixmap()
  pixmap.loadFromData(icon_data)
  return QIcon(pixmap)

class DateAxisItem(AxisItem):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.setLabel(text='Time')

  def tickStrings(self, values, scale, spacing):
    return [datetime.fromtimestamp(value).strftime("%H:%M:%S") for value in values]

class EdgeNodeLauncher(QWidget, _DockerUtilsMixin):
  def __init__(self):
    super().__init__()

    self._current_stylesheet = DARK_STYLESHEET
    self.__last_plot_data = None
    
    self.__version__ = __version__
    self.__last_timesteps = []
    self._icon = get_icon_from_base64(ICON_BASE64)
    
    self.initUI()

    if not self.check_docker():
      sys.exit(1)
    
    self.timer = QTimer(self)
    self.timer.timeout.connect(self.refresh_all)
    self.timer.start(REFRESH_TIME)  # Refresh every 10 seconds

    self.plot_data()  # Initial plot
    
    self.showMaximized()
    self.update_toggle_button_text()
    return
  
  def add_log(self, line):
    self.logView.append(line)
    return
  
  def center(self):
    screen_geometry = QApplication.desktop().screenGeometry()
    x = (screen_geometry.width() - self.width()) // 2
    y = (screen_geometry.height() - self.height()) // 2
    self.move(x, y)
    return

  def set_windows_taskbar_icon(self):
    import ctypes
    myappid = 'naeural.edge_node_launcher'  # arbitrary string
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    return
  
  def initUI(self):
    HEIGHT = 1100
    self.setWindowTitle(WINDOW_TITLE)
    self.setGeometry(0, 0, 1800, HEIGHT)
    self.center()

    main_layout = QHBoxLayout(self)

    # Left menu layout with fixed width
    menu_widget = QWidget()
    menu_widget.setFixedWidth(300)  # Set the fixed width here
    menu_layout = QVBoxLayout(menu_widget)
    menu_layout.setAlignment(Qt.AlignTop)
    
    top_button_area = QVBoxLayout()

    self.toggleButton = QPushButton(LAUNCH_CONTAINER_BUTTON_TEXT)
    self.toggleButton.clicked.connect(self.toggle_container)
    top_button_area.addWidget(self.toggleButton)

    self.dapp_button = QPushButton(DAPP_BUTTON_TEXT)
    self.dapp_button.clicked.connect(self.dapp_button_clicked)
    top_button_area.addWidget(self.dapp_button)

    self.explorer_button = QPushButton(EXPLORER_BUTTON_TEXT)
    self.explorer_button.clicked.connect(self.explorer_button_clicked)
    top_button_area.addWidget(self.explorer_button)


    menu_layout.addLayout(top_button_area)

    # Spacer to push bottom_button_area to the bottom
    menu_layout.addSpacerItem(QSpacerItem(20, int(HEIGHT * 0.75), QSizePolicy.Minimum, QSizePolicy.Expanding))


    # Bottom button area
    bottom_button_area = QVBoxLayout()
    
    ## info box
    info_box = QFrame()
    info_box.setFrameShape(QFrame.Box)
    info_box.setFrameShadow(QFrame.Sunken)
    info_box.setLineWidth(4)
    info_box.setMidLineWidth(1)
    info_box_layout = QVBoxLayout()

    self.addressDisplay = QLabel('')
    self.addressDisplay.setFont(QFont("Courier New"))
    info_box_layout.addWidget(self.addressDisplay)

    self.nameDisplay = QLabel('')
    self.nameDisplay.setFont(QFont("Courier New"))
    info_box_layout.addWidget(self.nameDisplay)

    self.node_uptime = QLabel('Up Time:')
    self.node_uptime.setFont(QFont("Courier New"))
    info_box_layout.addWidget(self.node_uptime)

    self.node_epoch = QLabel('Epoch:')
    self.node_epoch.setFont(QFont("Courier New"))
    info_box_layout.addWidget(self.node_epoch)

    self.node_epoch_avail = QLabel('Epoch avail:')
    self.node_epoch_avail.setFont(QFont("Courier New"))
    info_box_layout.addWidget(self.node_epoch_avail)
    
    info_box.setLayout(info_box_layout)
    bottom_button_area.addWidget(info_box)
    
    ## buttons
    self.copyButton = QPushButton(COPY_ADDRESS_BUTTON_TEXT)
    self.copyButton.clicked.connect(self.copy_address)
    bottom_button_area.addWidget(self.copyButton)

    self.envEditButton = QPushButton(EDIT_ENV_BUTTON_TEXT)
    self.envEditButton.clicked.connect(self.edit_env_file)
    bottom_button_area.addWidget(self.envEditButton)
    
    self.deleteButton = QPushButton(DELETE_AND_RESTART_BUTTON_TEXT)
    self.deleteButton.clicked.connect(self.delete_and_restart)
    bottom_button_area.addWidget(self.deleteButton)

    # Toggle theme button
    self.themeToggleButton = QPushButton('Switch to Light Theme')
    self.themeToggleButton.clicked.connect(self.toggle_theme)
    bottom_button_area.addWidget(self.themeToggleButton)    

    bottom_button_area.addStretch()
    menu_layout.addLayout(bottom_button_area)
    
    main_layout.addWidget(menu_widget)  # Add the fixed-width widget

    # Right side layout (for graphs)
    self.left_panel = QWidget()
    left_panel_layout = QVBoxLayout()
    
    # the graph area
    self.graphView = QWidget()
    graph_layout = QGridLayout()
    
    self.cpu_plot = pg.PlotWidget() #background='#243447')
    self.memory_plot = pg.PlotWidget() #background='#243447')
    self.gpu_plot = pg.PlotWidget() #background='#243447')
    self.gpu_memory_plot = pg.PlotWidget() #background='#243447')
    
    graph_layout.addWidget(self.cpu_plot, 0, 0)
    graph_layout.addWidget(self.memory_plot, 0, 1)
    graph_layout.addWidget(self.gpu_plot, 1, 0)
    graph_layout.addWidget(self.gpu_memory_plot, 1, 1)
    
    self.graphView.setLayout(graph_layout)
    left_panel_layout.addWidget(self.graphView)
    
    # the log scroll text area
    self.logView = QTextEdit()
    self.logView.setReadOnly(True)
    self.logView.setStyleSheet(self._current_stylesheet)
    self.logView.setFixedHeight(150)
    self.logView.setFont(QFont("Courier New"))
    left_panel_layout.addWidget(self.logView)      
    
    self.left_panel.setLayout(left_panel_layout)
    main_layout.addWidget(self.left_panel)

    self.setLayout(main_layout)
    self.refresh_local_address()
    self.apply_stylesheet()
    
    self.setWindowIcon(self._icon)
    self.set_windows_taskbar_icon()
    return
  
  def toggle_theme(self):
    if self._current_stylesheet == DARK_STYLESHEET:
      self._current_stylesheet = LIGHT_STYLESHEET
      self.themeToggleButton.setText('Switch to Dark Theme')
    else:
      self._current_stylesheet = DARK_STYLESHEET
      self.themeToggleButton.setText('Switch to Light Theme')
    self.apply_stylesheet()
    self.plot_graphs()
    return  

  def apply_stylesheet(self):
    self.setStyleSheet(self._current_stylesheet)
    self.logView.setStyleSheet(self._current_stylesheet)
    self.cpu_plot.setBackground(None)  # Reset the background to let the stylesheet take effect
    self.memory_plot.setBackground(None)
    self.gpu_plot.setBackground(None)
    self.gpu_memory_plot.setBackground(None)
    return

  def toggle_container(self):
    if self.is_container_running():
      self.stop_container()
    else:
      self.launch_container()
    self.update_toggle_button_text()
    return

  def update_toggle_button_text(self):
    if self.is_container_running():
      self.toggleButton.setText(STOP_CONTAINER_BUTTON_TEXT)
      self.toggleButton.setStyleSheet("background-color: red; color: white;")
    else:
      self.toggleButton.setText(LAUNCH_CONTAINER_BUTTON_TEXT)
      self.toggleButton.setStyleSheet("background-color: green; color: white;")
    return

  def edit_env_file(self):
    env_content = ''
    try:
      with open(self.env_file, 'r') as file:
        env_content = file.read()
    except FileNotFoundError:
      pass

    # Create the text edit widget with Courier New font and light font color
    text_edit = QTextEdit()
    text_edit.setText(env_content)
    text_edit.setFont(QFont("Courier New", 12))
    text_edit.setStyleSheet("color: #FFFFFF; background-color: #0D1F2D;")

    # Create the dialog
    dialog = QDialog(self)
    dialog.setWindowTitle('Edit .env File')
    dialog.setGeometry(0, 0, 1000, 900)  # Enlarge the edit window

    # Center the dialog on the screen
    screen_geometry = QApplication.desktop().screenGeometry()
    x = (screen_geometry.width() - dialog.width()) // 2
    y = (screen_geometry.height() - dialog.height()) // 2
    dialog.move(x, y)

    dialog_layout = QVBoxLayout()
    dialog_layout.addWidget(text_edit)

    # Save button
    save_button = QPushButton('Save')
    save_button.clicked.connect(lambda: self.save_env_file(text_edit.toPlainText(), dialog))
    dialog_layout.addWidget(save_button)

    dialog.setLayout(dialog_layout)
    dialog.exec_()
    return

  def save_env_file(self, content, dialog):
    with open(self.env_file, 'w') as file:
      file.write(content)
    dialog.accept()
    return
  
  def check_data(self, data):
    result = False
    if 'timestamps' in data:
      start_time = data['timestamps'][0] 
      end_time = data['timestamps'][-1]
      current_timestamps = data['timestamps'].copy()
      if current_timestamps != self.__last_timesteps:
        self.__last_timesteps = current_timestamps
        data_size = len(data['timestamps'])
        if data_size > 0 and data_size > MAX_HISTORY_QUEUE:
          for key in data:
            data[key] = data[key][-MAX_HISTORY_QUEUE:]
        start_time = data['timestamps'][0] 
        end_time = data['timestamps'][-1]
        self.add_log('Data loaded & cleaned: {} timestamps from {} to {}'.format(
          len(data['timestamps']), start_time, end_time)
        )
        result = True
    return result

  def plot_data(self):
    data_path = os.path.join(self.volume_path, LOCAL_HISTORY_FILE)
    try:
      if os.path.exists(data_path):
        with open(data_path, 'r') as file:
          data = json.load(file)
        if self.check_data(data):
          self.plot_graphs(data)
      else:
        self.plot_graphs(None)
    except FileNotFoundError:
      self.plot_graphs(None)
    return  


  def plot_graphs(self, data=None, limit=100):
    if data is None:
      data = self.__last_plot_data
    else:
      self.__last_plot_data = deepcopy(data)
      
    timestamps = [datetime.fromisoformat(ts).timestamp() for ts in data['timestamps'][-limit:]] if data and 'timestamps' in data else []

    def update_plot(plot, timestamps, values, label, color):
      plot.clear()
      plot.addLegend()
      if values:
        values = values[-limit:]
        plot.plot(timestamps, values, pen=pg.mkPen(color=color, width=2), name=label)
      else:
        plot.plot([0], [0], pen=None, symbol='o', symbolBrush=color, name='NO DATA')
      plot.setLabel('left', text=label)
      plot.setLabel('bottom', text='Time')
      plot.getAxis('bottom').autoVisible = False
      return

    # Plot CPU Load
    self.cpu_plot.getAxis('bottom').setTickSpacing(60, 10)
    self.cpu_plot.getAxis('bottom').setStyle(tickTextOffset=10)
    self.cpu_plot.setAxisItems({'bottom': DateAxisItem(orientation='bottom')})
    self.cpu_plot.setTitle('CPU Load')
    update_plot(self.cpu_plot, timestamps, data.get('cpu_load', []) if data else [], 'CPU Load', 'w' if self._current_stylesheet == DARK_STYLESHEET else 'k')

    # Plot Memory Load
    self.memory_plot.getAxis('bottom').setTickSpacing(60, 10)
    self.memory_plot.getAxis('bottom').setStyle(tickTextOffset=10)
    self.memory_plot.setAxisItems({'bottom': DateAxisItem(orientation='bottom')})
    self.memory_plot.setTitle('Memory Load')
    # update_plot(self.memory_plot, timestamps, data.get('total_memory', []) if data else [], 'Total Memory', 'y')
    update_plot(self.memory_plot, timestamps, data.get('occupied_memory', []) if data else [], 'Occupied Memory', 'w' if self._current_stylesheet == DARK_STYLESHEET else 'k')

    # Plot GPU Load if available
    self.gpu_plot.getAxis('bottom').setTickSpacing(60, 10)
    self.gpu_plot.getAxis('bottom').setStyle(tickTextOffset=10)
    self.gpu_plot.setAxisItems({'bottom': DateAxisItem(orientation='bottom')})
    self.gpu_plot.setTitle('GPU Load')
    update_plot(self.gpu_plot, timestamps, data.get('gpu_load', []) if data else [], 'GPU Load', 'w' if self._current_stylesheet == DARK_STYLESHEET else 'k')

    # Plot GPU Memory Load if available
    self.gpu_memory_plot.getAxis('bottom').setTickSpacing(60, 10)
    self.gpu_memory_plot.getAxis('bottom').setStyle(tickTextOffset=10)
    self.gpu_memory_plot.setAxisItems({'bottom': DateAxisItem(orientation='bottom')})
    self.gpu_memory_plot.setTitle('GPU Memory Load')
    # update_plot(self.gpu_memory_plot, timestamps, data.get('gpu_total_memory', []) if data else [], 'Total GPU Memory', 'y')
    update_plot(self.gpu_memory_plot, timestamps, data.get('gpu_occupied_memory', []) if data else [], 'Occupied GPU Memory', 'w' if self._current_stylesheet == DARK_STYLESHEET else 'k')
    return



  def refresh_local_address(self):
    address_path = os.path.join(self.volume_path, LOCAL_ADDRESS_FILE)
    try:
      with open(address_path, 'r') as file:
        address_info = [x for x in file.read().split(' ') if len(x) > 0]
        if len(address_info) == 0:
          raise FileNotFoundError
        if address_info[0] != self.node_addr:
          self.node_addr = address_info[0]
          self.node_name = address_info[1] if len(address_info) > 1 else ''
          str_display = address_info[0][:8] + '...' + address_info[0][-8:]
          self.addressDisplay.setText('Addr: ' + str_display)
          self.nameDisplay.setText('Name: ' + address_info[1] if len(address_info) > 1 else '')
          self.add_log(f'Local address updated: {self.node_addr} : {self.node_name}')
          
          # update uptime, epoch and epoch avail
          uptime = 0
          node_epoch = 0
          node_epoch_avail = 0
          self.node_uptime.setText(f'Up Time: {uptime}')
          self.node_epoch.setText(f'Epoch: {node_epoch}')
          self.node_epoch_avail.setText(f'Epoch avail: {node_epoch_avail}')
        # endif new address
      # endwith open                    
    except FileNotFoundError:
      self.addressDisplay.setText('Address file not found.')
      self.nameDisplay.setText('')
    return

  def copy_address(self):
    clipboard = QApplication.clipboard()
    clipboard.setText(self.addressDisplay.text())
    return
    
  def refresh_all(self):
    t0 = time()
    self.refresh_local_address()
    t1 = time()
    self.plot_data()
    t2 = time()
    self.update_toggle_button_text()
    t3 = time()
    self.add_log(f'Time taken: {t1 - t0:.2f}s (refresh_local_address), {t2 - t1:.2f}s (plot_data), {t3 - t2:.2f}s (update_toggle_button_text)')
    return    



  def dapp_button_clicked(self):
    return
  
  
  def explorer_button_clicked(self):
    return
#!/usr/bin/env python3
"""Show activity and drowsiness with automatic topic discovery retries."""

import json
import os
from pathlib import Path
import signal
import sys
import threading
import time

from python_qt_binding.QtCore import QTimer
from python_qt_binding.QtWidgets import QApplication, QMainWindow
import rclpy
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from rqt_plot.data_plot import DataPlot
from rqt_plot.plot_widget import PlotWidget
from std_msgs.msg import Float32


def main():
    app = QApplication(sys.argv)
    rclpy.init(args=[], signal_handler_options=SignalHandlerOptions.NO)
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    node = Node('activity_live_plot')
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    topics = ('/activity', '/drowsiness')
    states = {topic: {'received': 0, 'value': None, 'last_receive': None} for topic in topics}

    def receive(msg, topic):
        state = states[topic]
        state.update(received=state['received'] + 1, value=msg.data,
                     last_receive=time.monotonic())

    for topic in topics:
        node.create_subscription(Float32, topic, lambda msg, t=topic: receive(msg, t), 10)
    widget = PlotWidget(node)
    plot = DataPlot(widget)
    plot.set_autoscale(x=False, y=False)
    plot.set_xlim([0, 60])
    plot.set_ylim([-0.05, 1.05])
    widget.switch_data_plot_widget(plot)
    widget.autoscroll_checkbox.setChecked(True)
    plot.autoscroll(True)
    window = QMainWindow()
    window.setWindowTitle('CRANE-X7 activity & drowsiness')
    window.setCentralWidget(widget)
    window.resize(900, 500)
    status_path = Path(os.environ.get('ROS_HOME', '/tmp/crane_x7_manual_ros')) / 'activity_plot_status.json'
    status_path.parent.mkdir(parents=True, exist_ok=True)
    view_initialized = False

    def update_status():
        nonlocal view_initialized
        # rqt's normal initial_topics are tried only once, before DDS discovery
        # or the broadcaster may be ready. Keep trying until the curve exists.
        status = {}
        labels = []
        for topic in topics:
            field = topic + '/data'
            if field not in widget._rosdata:
                widget.add_topic(field)
            state = states[topic]
            value = state['value']
            age = None if state['last_receive'] is None else time.monotonic() - state['last_receive']
            name = 'Activity' if topic == '/activity' else 'Drowsiness'
            if value is None:
                labels.append(f'{name}: waiting for data')
            elif age > 1:
                labels.append(f'{name}: no new data for {age:.1f}s')
            else:
                labels.append(f'{name}: {value:.3f} ({state["received"]} received)')
            curve = plot._curves.get(field, {})
            status[topic] = {
                'received': state['received'], 'value': value,
                'age_seconds': age, 'curve_registered': bool(curve),
                'curve_samples': len(curve.get('x', [])),
            }
        window.statusBar().showMessage('    |    '.join(labels))
        if not view_initialized and any(s['curve_samples'] for s in status.values()):
            # rqt resets empty-plot limits while discovering topics. Set the
            # one-minute window again once real samples exist.
            latest = max(c['x'][-1] for c in plot._curves.values() if len(c['x']))
            plot.set_xlim([latest - 60.0, latest])
            view_initialized = True
        status['timer_active'] = widget._update_plot_timer.isActive()
        status_path.write_text(json.dumps(status) + '\n')
        snapshot = os.environ.get('CRANE_ACTIVITY_PLOT_SNAPSHOT')
        curve = plot._curves.get('/drowsiness/data', {})
        if (snapshot and not Path(snapshot).exists()
                and len(curve.get('y', [])) > 20
                and '/activity/data' in plot._curves
                and max(plot._curves['/activity/data']['y'], default=0.0) > 0.9
                and states['/activity']['value'] is not None
                and states['/activity']['value'] < 0.1):
            window.grab().save(snapshot)

    def spin():
        try:
            executor.spin()
        except ExternalShutdownException:
            pass

    worker = threading.Thread(target=spin, daemon=True)
    worker.start()
    timer = QTimer(window)
    timer.timeout.connect(update_status)
    timer.start(250)
    window.show()
    try:
        app.exec_()
    finally:
        timer.stop()
        executor.shutdown()
        worker.join(timeout=2)
        widget.clean_up_subscribers()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()

# The MIT License (MIT)
#
# Copyright (c) 2014-2015 WUSTL ZPLAB
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Authors: Erik Hvatum <ice.rikh@gmail.com>

from PyQt5 import Qt
import ris_widget
import ris_widget.image
import ris_widget.layer
import ris_widget.ris_widget
import ris_widget.qwidgets.layer_table
from .. import scope_client

# Show layer name column in LayerTable
ris_widget.qwidgets.layer_table.LayerTableModel.PROPERTIES.insert(
    ris_widget.qwidgets.layer_table.LayerTableModel.PROPERTIES.index('opacity') + 1, 'name')

class ScopeViewerQtObject(ris_widget.ris_widget.RisWidgetQtObject):
    RW_LIVE_STREAM_BINDING_LIVE_UPDATE_EVENT = Qt.QEvent.registerEventType()

    def __init__(
            self,
            app_prefs_name,
            app_prefs_version,
            window_title,
            parent,
            window_flags,
            msaa_sample_count,
            layers,
            layer_selection_model,
            scope,
            scope_properties,
            **kw):
        super().__init__(
            app_prefs_name,
            app_prefs_version,
            window_title,
            parent,
            window_flags,
            msaa_sample_count,
            layers,
            layer_selection_model,
            **kw)
        self.scope = scope
        self.scope_toolbar = self.addToolBar('Scope')
        self.live_streamer = scope_client.LiveStreamer(scope, scope_properties, self.post_live_update)
        self.get_live_target_layer()

    def event(self, e):
        # This is called by the main QT event loop to service the event posted in post_live_update().
        if e.type() == self.RW_LIVE_STREAM_BINDING_LIVE_UPDATE_EVENT:
            image_data, timestamp, frame_no = self.live_streamer.get_image()
            target_layer = self.get_live_target_layer()
            target_layer.image = ris_widget.image.Image(
                image_data,
                mask=self.layer_stack.imposed_image_mask,
                is_twelve_bit=self.live_streamer.bit_depth == '12 Bit')
            return True
        return super().event(e)

    def post_live_update(self):
        # posting an event does not require calling thread to have an event loop,
        # unlike sending a signal
        Qt.QCoreApplication.postEvent(self, Qt.QEvent(self.RW_LIVE_STREAM_BINDING_LIVE_UPDATE_EVENT))

    def get_live_target_layer(self):
        """The first Layer in self.layers with name "Live Target" is returned.  If self.layers contains no Layer with name
        "Live Target", one is created, inserted at index 0, and returned."""
        if self.layers is None:
            self.layers = []
        else:
            for layer in self.layers:
                if layer.name == 'Live Target':
                    return layer
        t = ris_widget.layer.Layer(name='Live Target')
        self.layers.insert(0, t)
        return t

class ScopeViewer(ris_widget.ris_widget.RisWidget):
    APP_PREFS_NAME = "ScopeViewer"
    COPY_REFS = ris_widget.ris_widget.RisWidget.COPY_REFS + [
        #'something'
    ]
    QT_OBJECT_CLASS = ScopeViewerQtObject

    @staticmethod
    def can_run(scope):
        return hasattr(scope, 'camera')

    def __init__(
            self,
            scope,
            scope_properties,
            window_title='Scope Viewer',
            parent=None,
            window_flags=Qt.Qt.WindowFlags(0),
            msaa_sample_count=2,
            show=True,
            layers = tuple(),
            layer_selection_model=None,
            **kw):
        super().__init__(
            window_title=window_title,
            parent=parent,
            window_flags=window_flags,
            msaa_sample_count=msaa_sample_count,
            show=show,
            layers=layers,
            layer_selection_model=layer_selection_model,
            scope=scope,
            scope_properties=scope_properties,
            **kw)
    #fooprop = ProxyProperty('fooprop', 'qt_object', ScopeViewerQtObject)
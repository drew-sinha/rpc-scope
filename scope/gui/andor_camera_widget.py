# This code is licensed under the MIT License (see LICENSE file for details)

from PyQt5 import Qt
from . import device_widget
from ..simple_rpc import rpc_client

INT_MIN, INT_MAX = 1, None
FLOAT_MIN, FLOAT_MAX, FLOAT_DECIMALS = 0, None, 3

# TODO: make advanced properties a separate widget.

class AndorCameraWidget(device_widget.DeviceWidget):
    PROPERTY_ROOT = 'scope.camera.'

    def __init__(self, scope, parent=None):
        super().__init__(scope, parent)
        self.camera_properties = dict(self.scope.camera.camera_properties)
        self.build_gui()

    def build_gui(self):
        self.setWindowTitle('Camera')
        properties = ['live_mode'] + self.scope.camera.basic_properties
        self.camera_properties['live_mode'] = dict(andor_type='Bool', read_only=False,
                units=None, range_hint=None)
        self.add_property_rows(properties)

    def add_property_rows(self, properties):
        form = Qt.QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(5)
        form.setLabelAlignment(Qt.Qt.AlignRight)
        form.setFieldGrowthPolicy(Qt.QFormLayout.ExpandingFieldsGrow)
        self.setLayout(form)
        for row, property in enumerate(properties):
            prop_data = self.camera_properties[property]
            self.make_widgets_for_property(row, property, prop_data)

    def make_widgets_for_property(self, row, property, prop_data):
        widget = self.make_widget(property, prop_data)
        units = prop_data['units']
        if units is not None:
            unit_label = Qt.QLabel(units)
            layout = Qt.QHBoxLayout()
            layout.addWidget(widget)
            layout.addWidget(unit_label)
            widget = layout
        self.layout().addRow(property + ':', widget)

    def make_widget(self, property, prop_data):
        if prop_data['read_only']:
            return self.make_readonly_widget(property)

        andor_type = prop_data['andor_type']
        if andor_type in {'Int', 'Float'}:
            return self.make_numeric_widget(property, prop_data)
        elif andor_type == 'Enum':
            return self.make_enum_widget(property)
        elif andor_type == 'Bool':
            return self.make_bool_widget(property)
        else: # we'll just treat it as readonly and show a string repr
            return self.make_readonly_widget(property)

    def make_readonly_widget(self, property):
        widget = Qt.QLabel()
        self.subscribe(self.PROPERTY_ROOT + property, callback=lambda value: widget.setText(str(value)), readonly=True)
        return widget

    def make_numeric_widget(self, property, prop_data):
        widget = Qt.QLineEdit()
        widget.setValidator(self.get_numeric_validator(property, prop_data))
        update = self.subscribe(self.PROPERTY_ROOT + property, callback=lambda value: widget.setText(str(value)))
        if update is None:
            raise TypeError('{} is not a writable property!'.format(property))
        coerce_type = int if prop_data['andor_type'] == 'Int' else float
        def editing_finished():
            try:
                value = coerce_type(widget.text())
                update(value)
            except ValueError as e: # from the coercion
                Qt.QMessageBox.warning(self, 'Invalid Value', e.args[0])
            except rpc_client.RPCError as e: # from the update
                if e.args[0].find('OUTOFRANGE') != -1:
                    min, max = getattr(self.scope.camera, property+'_range')
                    if min is None:
                        min = '?'
                    if max is None:
                        max = '?'
                    error = 'Given the camera state, {} must be in the range [{}, {}].'.format(property, min, max)
                elif e.args[0].find('NOTWRITABLE') != -1:
                    error = 'Given the camera state, {} is not modifiable.'.format(property)
                else:
                    error = 'Could not set {} ({}).'.format(property, e.args[0])
                Qt.QMessageBox.warning(self, 'Invalid Value', error)
        widget.editingFinished.connect(editing_finished)
        return widget

    def get_numeric_validator(self, property, prop_data):
        andor_type = prop_data['andor_type']
        range_hint = prop_data['range_hint']
        if andor_type == 'Float':
            validator = Qt.QDoubleValidator()
            if range_hint is not None:
                min, max, decimals = range_hint
            else:
                min, max, decimals = FLOAT_MIN, FLOAT_MAX, FLOAT_DECIMALS
            if decimals is not None:
                validator.setDecimals(decimals)
        if andor_type == 'Int':
            validator = Qt.QIntValidator()
            if range_hint is not None:
                min, max = range_hint
            else:
                min, max = INT_MIN, INT_MAX
        if min is not None:
            validator.setBottom(min)
        if max is not None:
            validator.setTop(max)
        return validator

    def make_enum_widget(self, property):
        widget = Qt.QComboBox()
        values = sorted(getattr(self.scope.camera, property+'_values').keys())
        indices = {v: i for i, v in enumerate(values)}
        widget.addItems(values)
        update = self.subscribe(self.PROPERTY_ROOT + property, callback=lambda value: widget.setCurrentIndex(indices[value]))
        if update is None:
            raise TypeError('{} is not a writable property!'.format(property))
        def changed(value):
            try:
                update(value)
            except rpc_client.RPCError as e:
                if e.args[0].find('NOTWRITABLE') != -1:
                    error = "Given the camera state, {} can't be changed.".format(property)
                elif e.args[0].find('NOTAVAILABLE') != -1:
                    accepted_values = sorted(k for k, v in getattr(self.scope.camera, property+'_values').items() if v)
                    error = 'Given the camera state, {} can only be one of [{}].'.format(property, ', '.join(accepted_values))
                else:
                    error = 'Could not set {} ({}).'.format(property, e.args[0])
                Qt.QMessageBox.warning(self, 'Invalid Value', error)
        widget.currentIndexChanged[str].connect(changed)
        return widget

    def make_bool_widget(self, property):
        widget = Qt.QCheckBox()
        update = self.subscribe(self.PROPERTY_ROOT + property, callback=widget.setChecked)
        if update is None:
            raise TypeError('{} is not a writable property!'.format(property))
        def changed(value):
            try:
                update(value)
            except rpc_client.RPCError as e:
                if e.args[0].find('NOTWRITABLE') != -1:
                    error = "Given the camera state, {} can't be changed.".format(property)
                else:
                    error = 'Could not set {} ({}).'.format(property, e.args[0])
                Qt.QMessageBox.warning(self, 'Invalid Value', error)
        widget.toggled.connect(changed)
        return widget


class AndorAdvancedCameraWidget(AndorCameraWidget):
    def build_gui(self):
        self.setWindowTitle('Adv. Camera')
        advanced_properties = sorted(self.camera_properties.keys() - set(self.scope.camera.basic_properties))
        self.add_property_rows(advanced_properties)

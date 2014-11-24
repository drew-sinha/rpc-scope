from .. import scope_configuration as _config

def _make_command(*elements):
    return ' '.join(map(str, elements))

def wait_high(pin):
    return _make_command('wh', pin)

def wait_low(pin):
    return _make_command('wl', pin)
    
def wait_change(pin):
    return _make_command('wc', pin)

def wait_time(time):
    return _make_command('wt', time)

def read_digital(pin):
    return _make_command('rd', pin)

def read_analog(pin):
    return _make_command('ra', pin)
    
def delay_ms(delay):
    return _make_command('dm', delay)

def delay_us(delay):
    return _make_command('du', delay)

def timer_begin():
    return _make_command('tb')

def timer_end():
    return _make_command('te')

def pwm(pin, value):
    return _make_command('pm', pin, value)

def set_high(pin):
    return _make_command('sh', pin)

def set_low(pin):
    return _make_command('sl', pin)
    
def set_tristate(pin):
    return _make_command('st', pin)

def char_transmit(byte):
    return _make_command('ct', byte)

def char_receive(cls):
    return _make_command('cr')

def loop(index, count):
    return _make_command('lo', index, count)

def goto(index):
    return _make_command('go', index)

def lumencor_lamps(**lamps):
    """Input keyword arguments must be lamp names specified in LUMENCOR_PINS
    keys. The values are either True to enable that lamp, False to disable,
    or None to do nothing (unspecified lamps are also not altered)."""
    command = []
    for lamp, enable in lamps.items():
        if enable is None:
            continue
        pin = _config.IOTool.LUMENCOR_PINS[lamp]
        if enable:
            command.append(set_high(pin))
        else:
            command.append(set_low(pin))
    return '\n'.join(command)

def transmitted_lamp(enable=None, intensity=None):
    """enable: True (lamp on), False (lamp off), or None (no change).
    intensity: None (no change) or value in the range [0, 255] for min to max.
    """
    command = []
    if pwm is not None:
        assert 0 <= intensity <= _config.IOTool.TL_PWM_MAX
        command.append(pwm(_config.IOTool.TL_PWM_PIN, intensity))
    if enable is not None:
        if enable:
            command.append(set_high(_config.IOTool.TL_ENABLE_PIN))
        else:
            command.append(set_low(_config.IOTool.TL_ENABLE_PIN))
    return '\n'.join(command)

def footpedal_wait():
    return wait_low(_config.IOTool.FOOTPEDAL_PIN)
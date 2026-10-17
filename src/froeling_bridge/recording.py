"""p4d applyConfigurationSpecials: mandatory internal UD recording.

This is an effective runtime policy, not a change to valuefacts.record.
"""
AUTOMATIC_UD_ADDRESSES = frozenset((1, 2, 3))


def automatic_recording(sensor, mode):
    return (mode in ('standalone', 'standalone-demo') and
            sensor['type'] == 'UD' and sensor['address'] in AUTOMATIC_UD_ADDRESSES)
